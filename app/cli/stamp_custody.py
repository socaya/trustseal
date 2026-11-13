"""Explicit operator-controlled stamp attestation issuance and verification.

Only approved, active, tenant-scoped stamp authority and previously finalized
PDFs can be attested. This does not render a graphic impression on the PDF.
"""
from datetime import datetime

import click
from flask import current_app
from flask.cli import AppGroup, with_appcontext
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.user import User
from app.models.pdf_finalization import FinalizedPdf
from app.models.stamp_custody import ManagedStamp, StampApplication, StampAttestation
from app.policies.api_access import is_admin
from app.services.documents.private_storage import check_object_digest, IngestionError
from app.services.platform_pdf_seal import inspect_signed_pdf, PdfFinalizationError
from app.services.event_delivery import enqueue
from app.services.stamp_attestation import (
    stamp_payload, issue_attestation, verify_attestation, trusted_stamp_key,
)
from app.services.signing_receipts import load_private_key, public_key_id

stamp_cli = AppGroup("stamp-custody")


def _operator(stamp, application):
    raw = current_app.config.get("STAMP_ATTESTATION_OPERATOR_ID")
    if raw is None or not str(raw).isdecimal():
        raise ValueError("Stamp issuance operator not configured")
    operator = db.session.get(User, int(raw))
    if (operator is None or not operator.is_active
            or operator.organization_id != stamp.organization_id
            or not is_admin(operator.id)
            or operator.id in (
                stamp.created_by_id, stamp.custodian_id,
                stamp.approved_by_id, application.requested_by_id,
                application.decided_by_id,
            )):
        raise ValueError("Independent active stamp issuance administrator required")
    return operator


def _verify_pdf(pdf):
    path = check_object_digest(pdf.object_key, pdf.output_sha256, current_app.config)
    status = inspect_signed_pdf(
        path.read_bytes(), current_app.config,
        expected_evidence_sha256=pdf.evidence_sha256,
        expected_certificate_sha256=pdf.certificate_sha256,
    )
    if not status["overall_valid"]:
        raise ValueError("Finalized document seal invalid")


@stamp_cli.command("issue")
@click.argument("application_id", type=int)
@with_appcontext
def issue(application_id):
    """Issue one cryptographically signed, separate stamp authority receipt."""
    if not current_app.config.get("STAMP_ATTESTATION_ENABLED", False):
        raise click.ClickException("Stamp attestation issuance is disabled")
    application = StampApplication.query.filter_by(id=application_id).with_for_update().first()
    if application is None:
        raise click.ClickException("Stamp application unavailable")
    existing = StampAttestation.query.filter_by(application_id=application.id).first()
    if existing:
        click.echo("Stamp attestation already exists: %s" % existing.id)
        db.session.rollback()
        return
    stamp = ManagedStamp.query.filter_by(
        id=application.stamp_id, organization_id=application.organization_id,
    ).with_for_update().first()
    pdf = db.session.get(FinalizedPdf, application.finalized_pdf_id)
    try:
        if (stamp is None or stamp.status != "active"
                or application.status != "approved"
                or pdf is None or pdf.organization_id != application.organization_id):
            raise ValueError("Stamp authority, approval or document is invalid")
        operator = _operator(stamp, application)
        _verify_pdf(pdf)
        signed_at = datetime.utcnow()
        payload = stamp_payload(stamp, application, pdf, operator.id, signed_at)
        private = load_private_key(current_app.config.get("STAMP_ATTESTATION_PRIVATE_KEY"))
        signed = issue_attestation(payload, private)
        trusted = trusted_stamp_key(current_app.config, signed["key_id"])
        if not verify_attestation(signed, trusted):
            raise ValueError("Stamp evidence self-verification failed")
        record = StampAttestation(
            application_id=application.id,
            stamp_id=stamp.id,
            organization_id=stamp.organization_id,
            operator_id=operator.id,
            payload=signed["payload"], algorithm=signed["algorithm"],
            key_id=signed["key_id"], signature=signed["signature"],
            created_at=signed_at,
        )
        db.session.add(record)
        db.session.flush()
        enqueue(
            event_type="stamp.attestation.issued",
            aggregate_type="stamp_application",
            aggregate_id=application.id,
            organization_id=application.organization_id,
            actor_id=operator.id,
            action="stamp.attestation.issued",
            idempotency_key="stamp-attestation:%s" % application.id,
        )
        db.session.commit()
    except (ValueError, OSError, TypeError, PdfFinalizationError, IngestionError, IntegrityError):
        db.session.rollback()
        raise click.ClickException("Stamp issuance prerequisites failed") from None
    click.echo("Issued stamp attestation: %s" % record.id)


@stamp_cli.command("verify")
@click.argument("attestation_id", type=int)
@with_appcontext
def verify(attestation_id):
    record = db.session.get(StampAttestation, attestation_id)
    if record is None:
        raise click.ClickException("Stamp attestation not found")
    try:
        key = trusted_stamp_key(current_app.config, record.key_id)
        if not verify_attestation(
            {"payload": record.payload, "signature": record.signature,
             "algorithm": record.algorithm, "key_id": record.key_id}, key
        ):
            raise ValueError("Signature invalid")
    except (ValueError, OSError, TypeError, KeyError):
        raise click.ClickException("Stamp cryptographic verification failed") from None
    click.echo("Stamp attestation cryptographically valid: %s" % record.id)
