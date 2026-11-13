"""Operator-only issuance of platform review attestations.

This CLI does not generate or alter PDFs. The key should live in a KMS/HSM in
production; this protected-file adapter is intended for controlled staging.
"""
import click
from flask import current_app
from flask.cli import AppGroup, with_appcontext
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.review_receipt import ReviewReceipt
from app.models.signer_decision import SignerDecision
from app.models.signing_envelope import SigningEnvelope, EnvelopeParticipant
from app.services.signing_receipts import (
    load_private_key, load_public_key, public_key_id,
    review_payload, sign_receipt, verify_receipt,
)
from app.blueprints.documents.api.signer_intent_api import _decision_digest

receipts_cli = AppGroup("receipts")


@receipts_cli.command("issue")
@click.argument("decision_id", type=int)
@with_appcontext
def issue(decision_id):
    """Issue one cryptographically signed platform review receipt."""
    decision = db.session.query(SignerDecision).filter_by(id=decision_id).with_for_update().first()
    if decision is None:
        raise click.ClickException("Review decision not found")
    existing = ReviewReceipt.query.filter_by(decision_id=decision.id).first()
    if existing:
        click.echo("Receipt already exists: %s" % existing.id)
        db.session.rollback()
        return

    envelope = db.session.get(SigningEnvelope, decision.envelope_id)
    participant = db.session.get(EnvelopeParticipant, decision.participant_id)
    if (envelope is None or participant is None or
            participant.envelope_id != envelope.id or
            participant.user_id != decision.user_id):
        db.session.rollback()
        raise click.ClickException("Inconsistent participant or envelope")
    try:
        expected = _decision_digest(
            envelope, participant, decision.user_id, decision.decision,
            consent_version=decision.consent_version,
        )
        if expected != decision.consent_sha256:
            raise ValueError("Review consent digest mismatch")
        private_key = load_private_key(current_app.config.get("REVIEW_RECEIPT_PRIVATE_KEY"))
        trusted_key = load_public_key(current_app.config.get("REVIEW_RECEIPT_PUBLIC_KEY"))
        if public_key_id(private_key.public_key()) != public_key_id(trusted_key):
            raise ValueError("Signing and verifier key mismatch")
        signed = sign_receipt(review_payload(envelope, participant, decision), private_key)
        if not verify_receipt(signed, trusted_key):
            raise ValueError("Generated receipt verification failed")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        db.session.rollback()
        raise click.ClickException("Issuance rejected: %s" % type(exc).__name__) from None

    record = ReviewReceipt(
        decision_id=decision.id,
        envelope_id=envelope.id,
        organization_id=envelope.organization_id,
        payload=signed["payload"], algorithm=signed["algorithm"],
        key_id=signed["key_id"], signature=signed["signature"],
    )
    db.session.add(record)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise click.ClickException("Concurrent receipt already exists") from None
    click.echo("Created platform review receipt: %s" % record.id)
