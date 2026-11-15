"""Operator-controlled finalization of fully acknowledged review envelopes.

Generates a certificate-backed *platform seal*. It does not sign on behalf
of each human participant. No HTTP endpoint can request finalization.

The actual sealing logic lives in :class:`app.services.envelopes.
EnvelopeOrchestrator`. This CLI is a thin, auditable wrapper so the same
flow runs identically whether invoked by an operator or (later) by an
authorized server-side task.
"""
import click
from flask import current_app
from flask.cli import AppGroup, with_appcontext

from app.extensions import db
from app.models.pdf_finalization import FinalizedPdf
from app.models.signing_envelope import SigningEnvelope
from app.services.documents.private_storage import (
    check_object_digest, IngestionError,
)
from app.services.envelopes.orchestrator import (
    EnvelopeOrchestrator, OrchestratorError,
)
from app.services.platform_pdf_seal import inspect_signed_pdf, PdfFinalizationError

pdf_seal_cli = AppGroup("pdf-seal")


def _operator(envelope):
    """Kept for backwards-compatibility with the legacy test harness.

    New callers must invoke :class:`EnvelopeOrchestrator` directly.
    """
    orchestrator = EnvelopeOrchestrator()
    return orchestrator._authorize_operator(envelope)  # noqa: SLF001


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
        # A platform seal now requires cryptographic proof from each assigned
        # signer-held key, not merely the platform's review receipt.
        endorsement = SignerEndorsement.query.filter_by(
            envelope_id=envelope.id, participant_id=participant.id
        ).first()
        if endorsement is None or endorsement.user_id != participant.user_id:
            raise PdfFinalizationError("Missing signer-controlled document endorsement")
        signer_key = db.session.get(SignerPublicKey, endorsement.signer_key_id)
        if signer_key is None or signer_key.user_id != participant.user_id:
            raise PdfFinalizationError("Signer public key record unavailable")
        try:
            expected_endorsement = endorsement_payload(
                envelope=envelope, participant=participant, decision=decision,
                fingerprint=signer_key.fingerprint,
                nonce=endorsement.signed_payload.get("nonce"),
            )
        except (ValueError, TypeError, AttributeError) as exc:
            raise PdfFinalizationError("Invalid signer endorsement context") from exc
        if (endorsement.signed_payload != expected_endorsement
                or not verify_detached(
                    signer_key.public_key_pem,
                    endorsement.signed_payload, endorsement.signature_b64
                )):
            raise PdfFinalizationError("Signer-controlled endorsement invalid")
        receipts_for_digest.append({
            "signer_endorsement": {
                "public_key_pem": signer_key.public_key_pem,
                "key_fingerprint": signer_key.fingerprint,
                "signed_payload": endorsement.signed_payload,
                "signature_b64": endorsement.signature_b64,
            },
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
    try:
        result = EnvelopeOrchestrator().finalize(envelope_id)
    except OrchestratorError as exc:
        if exc.reason == "envelope_not_found":
            raise click.ClickException("Envelope not found") from None
        if exc.reason == "envelope_not_prepared":
            raise click.ClickException("Envelope is not prepared") from None
        raise click.ClickException(f"Finalization failed: {exc.reason}") from None
    if result.already_finalized:
        click.echo("Already finalized: %s" % result.finalized_pdf_id)
    else:
        click.echo("Finalized platform-sealed PDF: %s" % result.finalized_pdf_id)


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
