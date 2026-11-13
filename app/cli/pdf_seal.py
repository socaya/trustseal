"""Operator-controlled finalization of fully acknowledged review envelopes.

Generates a certificate-backed *platform seal*. It does not sign on behalf
of each human participant. No HTTP endpoint can request finalization.
"""
import hashlib
import io

import click
from flask import current_app
from flask.cli import AppGroup, with_appcontext
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.signing_envelope import SigningEnvelope, EnvelopeParticipant
from app.models.signer_decision import SignerDecision
from app.models.review_receipt import ReviewReceipt
from app.models.documents.document_blob import DocumentBlob
from app.models.pdf_finalization import FinalizedPdf
from app.services.documents.private_storage import (
    check_object_digest, store_scanned_pdf, cleanup_object, IngestionError,
)
from app.services.platform_pdf_seal import seal_pdf, inspect_signed_pdf, PdfFinalizationError
from app.services.signing_receipts import resolve_trusted_public_key, verify_receipt, review_payload
from app.services.event_delivery import enqueue
from app.services.platform_review_evidence import canonical_evidence_bundle, evidence_digest

pdf_seal_cli = AppGroup("pdf-seal")


def _complete_review(envelope):
    participants = EnvelopeParticipant.query.filter_by(
        envelope_id=envelope.id
    ).order_by(EnvelopeParticipant.signing_order).all()
    if not participants:
        raise PdfFinalizationError("Envelope has no participants")
    receipts_for_digest = []
    for participant in participants:
        decision = SignerDecision.query.filter_by(participant_id=participant.id).first()
        if (decision is None or decision.envelope_id != envelope.id
                or decision.user_id != participant.user_id
                or decision.decision != "acknowledged"
                or decision.document_sha256 != envelope.document_sha256):
            raise PdfFinalizationError("All participants must acknowledge the exact PDF")
        receipt = ReviewReceipt.query.filter_by(decision_id=decision.id).first()
        if receipt is None:
            raise PdfFinalizationError("Every review must have a signed receipt")
        detached = {
            "payload": receipt.payload, "signature": receipt.signature,
            "algorithm": receipt.algorithm, "key_id": receipt.key_id,
        }
        key = resolve_trusted_public_key(current_app.config, receipt.key_id)
        if not verify_receipt(detached, key):
            raise PdfFinalizationError("Review receipt signature invalid")
        if receipt.payload != review_payload(envelope, participant, decision):
            raise PdfFinalizationError("Review receipt evidence mismatch")
        receipts_for_digest.append({
            "participant_id": participant.id,
            "signing_order": participant.signing_order,
            "review_decision_id": decision.id,
            "payload": receipt.payload,
            "algorithm": receipt.algorithm,
            "key_id": receipt.key_id,
            "signature": receipt.signature,
        })
    bundle = canonical_evidence_bundle(envelope.id, receipts_for_digest)
    return evidence_digest(bundle)


@pdf_seal_cli.command("finalize")
@click.argument("envelope_id", type=int)
@with_appcontext
def finalize(envelope_id):
    """Seal one reviewed PDF with the configured platform certificate."""
    envelope = SigningEnvelope.query.filter_by(id=envelope_id).with_for_update().first()
    if envelope is None:
        raise click.ClickException("Envelope not found")
    existing = FinalizedPdf.query.filter_by(envelope_id=envelope.id).first()
    if existing is not None:
        click.echo("Already finalized: %s" % existing.id)
        db.session.rollback()
        return
    if envelope.state != "prepared":
        db.session.rollback()
        raise click.ClickException("Envelope is not prepared")
    object_key = None
    try:
        evidence_digest = _complete_review(envelope)
        original = db.session.get(DocumentBlob, envelope.document_blob_id)
        if (original is None or original.document_id != envelope.document_id
                or original.sha256 != envelope.document_sha256):
            raise PdfFinalizationError("Frozen source manifest mismatch")
        source = check_object_digest(
            original.object_key, original.sha256, current_app.config
        ).read_bytes()
        if hashlib.sha256(source).hexdigest() != envelope.document_sha256:
            raise PdfFinalizationError("Source bytes do not match envelope")
        signed, certificate_sha256, _status = seal_pdf(
            source, current_app.config, evidence_digest
        )
        object_key, _name, size, output_digest, _scanner = store_scanned_pdf(
            io.BytesIO(signed),
            "TrustSeal-sealed-envelope-%s.pdf" % envelope.id,
            current_app.config,
        )
        record = FinalizedPdf(
            envelope_id=envelope.id,
            organization_id=envelope.organization_id,
            source_blob_id=original.id,
            source_sha256=original.sha256,
            evidence_sha256=evidence_digest,
            object_key=object_key,
            output_sha256=output_digest,
            output_size=size,
            certificate_sha256=certificate_sha256,
            signature_field="TrustSealPlatformSeal",
            profile="platform_pades_b_b",
        )
        db.session.add(record)
        db.session.flush()
        enqueue(
            event_type="platform.pdf.sealed",
            aggregate_type="envelope",
            aggregate_id=envelope.id,
            organization_id=envelope.organization_id,
            actor_id=None,
            action="platform.pdf.sealed.system_operator",
            idempotency_key="platform-pdf-sealed:%s" % envelope.id,
        )
        db.session.commit()
    except (PdfFinalizationError, IngestionError, ValueError, OSError, IntegrityError) as exc:
        db.session.rollback()
        if object_key:
            try:
                cleanup_object(object_key, current_app.config)
            except Exception:
                current_app.logger.exception("Signed PDF orphan cleanup failed")
        raise click.ClickException("Finalization failed: %s" % type(exc).__name__) from None
    click.echo("Finalized platform-sealed PDF: %s" % record.id)


@pdf_seal_cli.command("verify")
@click.argument("envelope_id", type=int)
@with_appcontext
def verify(envelope_id):
    """Recheck stored output digest and trusted embedded PDF signature."""
    record = FinalizedPdf.query.filter_by(envelope_id=envelope_id).first()
    if record is None:
        raise click.ClickException("No finalized PDF for envelope")
    try:
        path = check_object_digest(record.object_key, record.output_sha256, current_app.config)
        status = inspect_signed_pdf(
            path.read_bytes(), current_app.config,
            expected_evidence_sha256=record.evidence_sha256,
        )
    except (IngestionError, PdfFinalizationError):
        raise click.ClickException("Finalized PDF integrity check failed") from None
    if not status["overall_valid"]:
        raise click.ClickException("Finalized PDF certificate validation failed")
    click.echo("Platform PDF seal verified: %s" % record.id)
