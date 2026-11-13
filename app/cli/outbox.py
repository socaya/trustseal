"""Operator-only outbox inspection and bounded dispatch commands.

Invocation: flask outbox status; flask outbox drain --limit 50
Only built-in, allowlisted internal event consumers are registered here.
Never call untrusted code based on an event's payload.
"""
import click
from flask.cli import AppGroup, with_appcontext
from app.extensions import db
from app.models.event_delivery import OutboxEvent
from app.models.documents.document import Document
from app.models.documents.document_snapshot import DocumentSnapshot
from app.models.documents.document_blob import DocumentBlob
from app.services.event_delivery import deliver_one

outbox_cli = AppGroup("outbox")


def _verify_document_event(payload, key):
    document_id = payload.get("aggregate_id")
    if type(document_id) is not int:
        raise ValueError("Invalid aggregate ID")
    doc = db.session.get(Document, document_id)
    if doc is None:
        raise ValueError("Document no longer exists")
    if key.startswith("document-snapshot:"):
        revision = int(key.rsplit(":", 1)[-1])
        if DocumentSnapshot.query.filter_by(document_id=doc.id, revision=revision).first() is None:
            raise ValueError("Missing snapshot manifest")
    elif key.startswith("document-file:"):
        revision = int(key.rsplit(":", 1)[-1])
        if DocumentBlob.query.filter_by(document_id=doc.id, revision=revision).first() is None:
            raise ValueError("Missing file manifest")
    # Internal consistency acknowledgement only; not an external notification.



def _verify_envelope_event(payload, key):
    from app.models.signing_envelope import SigningEnvelope, EnvelopeParticipant
    envelope_id = payload.get("aggregate_id")
    if type(envelope_id) is not int:
        raise ValueError("Invalid envelope ID")
    envelope = db.session.get(SigningEnvelope, envelope_id)
    if envelope is None:
        raise ValueError("Envelope not found")
    if key.startswith("envelope-prepared:"):
        if envelope.state not in ("prepared", "cancelled"):
            raise ValueError("Envelope has not been prepared")
        if not EnvelopeParticipant.query.filter_by(envelope_id=envelope.id).first():
            raise ValueError("Prepared envelope lacks participants")
    if key.startswith("envelope-cancelled:") and envelope.state != "cancelled":
        raise ValueError("Envelope cancellation missing")



def _verify_signer_review(payload, key):
    from app.models.signing_envelope import SigningEnvelope
    from app.models.signer_decision import SignerDecision
    from app.blueprints.documents.api.signer_intent_api import _decision_digest
    envelope_id = payload.get("aggregate_id")
    if type(envelope_id) is not int:
        raise ValueError("Invalid review envelope ID")
    envelope = db.session.get(SigningEnvelope, envelope_id)
    if envelope is None:
        raise ValueError("Missing review envelope")
    participant_id = int(key.rsplit(":", 1)[-1])
    decision = SignerDecision.query.filter_by(
        envelope_id=envelope.id, participant_id=participant_id
    ).first()
    if decision is None:
        raise ValueError("Missing signer review decision")
    from app.models.signing_envelope import EnvelopeParticipant
    participant = db.session.get(EnvelopeParticipant, participant_id)
    if participant is None or participant.envelope_id != envelope.id:
        raise ValueError("Review participant mismatch")
    if decision.consent_sha256 != _decision_digest(
        envelope, participant, decision.user_id, decision.decision,
        consent_version=decision.consent_version
    ):
        raise ValueError("Signer review intent digest mismatch")


def _verify_review_receipt_event(payload, key):
    from app.models.review_receipt import ReviewReceipt
    envelope_id = payload.get("aggregate_id")
    if type(envelope_id) is not int or not key.startswith("review-receipt:"):
        raise ValueError("Invalid review receipt event")
    decision_id = int(key.rsplit(":", 1)[-1])
    item = ReviewReceipt.query.filter_by(
        decision_id=decision_id, envelope_id=envelope_id
    ).first()
    if item is None:
        raise ValueError("Missing issued review receipt")
    # This consistency check does not replace standalone cryptographic
    # verification with the pinned key.


def _verify_pdf_seal_event(payload, key):
    from app.models.pdf_finalization import FinalizedPdf
    envelope_id = payload.get("aggregate_id")
    if type(envelope_id) is not int or key != "platform-pdf-sealed:%s" % envelope_id:
        raise ValueError("Unexpected PDF seal event")
    artifact = FinalizedPdf.query.filter_by(envelope_id=envelope_id).first()
    if artifact is None:
        raise ValueError("Missing platform PDF artifact")
    if artifact.profile != "platform_pades_b_b":
        raise ValueError("Unsupported platform PDF profile")


def _verify_signer_crypto_event(payload, key):
    from app.models.signer_cryptographic import SignerPublicKey, SignerEndorsement
    from app.models.signing_envelope import SigningEnvelope, EnvelopeParticipant
    from app.models.signer_decision import SignerDecision
    from app.services.signer_crypto import verify_detached, endorsement_payload
    aggregate = payload.get("aggregate_id")
    if type(aggregate) is not int:
        raise ValueError("Invalid cryptographic event aggregate")
    if key.startswith("signer-key-"):
        signer_key = db.session.get(SignerPublicKey, aggregate)
        if signer_key is None:
            raise ValueError("Missing signer key")
        if key.startswith("signer-key-revoked:") and signer_key.revoked_at is None:
            raise ValueError("Signer key not revoked")
        return
    if not key.startswith("signer-document-endorsed:"):
        raise ValueError("Unknown signer event")
    participant_id = int(key.rsplit(":", 1)[-1])
    proof = SignerEndorsement.query.filter_by(
        envelope_id=aggregate, participant_id=participant_id
    ).first()
    if proof is None:
        raise ValueError("Missing signer endorsement")
    credential = db.session.get(SignerPublicKey, proof.signer_key_id)
    envelope = db.session.get(SigningEnvelope, proof.envelope_id)
    participant = db.session.get(EnvelopeParticipant, proof.participant_id)
    decision = SignerDecision.query.filter_by(participant_id=participant_id).first()
    if any(item is None for item in (credential, envelope, participant, decision)):
        raise ValueError("Signer cryptographic evidence incomplete")
    expected = endorsement_payload(
        envelope=envelope, participant=participant, decision=decision,
        fingerprint=credential.fingerprint,
        nonce=proof.signed_payload.get("nonce"),
    )
    if (proof.user_id != credential.user_id
            or expected != proof.signed_payload
            or not verify_detached(
                credential.public_key_pem, proof.signed_payload, proof.signature_b64
            )):
        raise ValueError("Signer endorsement cryptographic validation failed")


def _verify_stamp_custody_event(payload, key):
    from app.models.stamp_custody import ManagedStamp, StampApplication, StampAttestation
    event_id = payload.get("aggregate_id")
    if type(event_id) is not int:
        raise ValueError("Invalid stamp event aggregate")
    if key.startswith(("stamp-registration:", "stamp-activated:", "stamp-revoked:")):
        stamp = db.session.get(ManagedStamp, event_id)
        if stamp is None:
            raise ValueError("Stamp registration missing")
        if key.startswith("stamp-activated:") and stamp.status not in ("active", "revoked"):
            raise ValueError("Stamp not approved")
        if key.startswith("stamp-revoked:") and stamp.status != "revoked":
            raise ValueError("Stamp not revoked")
        return
    if key.startswith(("stamp-use-requested:", "stamp-use-decision:", "stamp-attestation:", "stamp-pdf:")):
        application = db.session.get(StampApplication, event_id)
        if application is None:
            raise ValueError("Stamp application missing")
        if key.startswith("stamp-use-decision:") and application.status == "pending":
            raise ValueError("Stamp decision missing")
        if key.startswith("stamp-attestation:"):
            receipt = StampAttestation.query.filter_by(application_id=application.id).first()
            if receipt is None:
                raise ValueError("Stamp attestation missing")
        if key.startswith("stamp-pdf:"):
            from app.models.stamped_pdf import StampedPdf
            receipt = StampAttestation.query.filter_by(application_id=application.id).first()
            if receipt is None or key != "stamp-pdf:%s" % receipt.id:
                raise ValueError("Stamp PDF attestation mismatch")
            stamped = StampedPdf.query.filter_by(stamp_attestation_id=receipt.id).first()
            if stamped is None or stamped.organization_id != application.organization_id:
                raise ValueError("Stamp PDF derivative unavailable")
        return
    raise ValueError("Stamp event has no recognized idempotency key")


def _verify_stamp_design_event(payload, key):
    from app.models.stamp_design import StampDesignVersion
    stamp_id = payload.get("aggregate_id")
    if type(stamp_id) is not int or not key.startswith("stamp-design-"):
        raise ValueError("Invalid stamp design event")
    try:
        design_id = int(key.rsplit(":", 1)[-1])
    except (ValueError, IndexError):
        raise ValueError("Invalid design event identity") from None
    item = StampDesignVersion.query.filter_by(
        id=design_id, stamp_id=stamp_id,
    ).first()
    if item is None:
        raise ValueError("Design version missing")
    if key.startswith("stamp-design-decision:") and item.state == "pending":
        raise ValueError("Design decision unavailable")


def _verify_preservation_event(payload, key):
    from app.models.evidence_preservation import (
        EvidenceRetention, EvidenceLegalHold, EvidenceCheckpoint,
    )
    aggregate = payload.get("aggregate_id")
    if type(aggregate) is not int:
        raise ValueError("Invalid preservation event")
    if key.startswith("evidence-retention:"):
        retention = db.session.get(EvidenceRetention, aggregate)
        if retention is None or key != "evidence-retention:%s" % retention.id:
            raise ValueError("Retention event invalid")
    elif key.startswith(("evidence-hold:", "evidence-hold-release:")):
        hold = db.session.get(EvidenceLegalHold, aggregate)
        if hold is None:
            raise ValueError("Legal hold unavailable")
        if key.startswith("evidence-hold-release:") and hold.released_at is None:
            raise ValueError("Release missing")
    elif key.startswith("evidence-checkpoint:"):
        from app.services.evidence_preservation import (
            verify_checkpoint, trusted_checkpoint_key,
        )
        from flask import current_app
        try:
            checkpoint_id = int(key.rsplit(":", 1)[-1])
        except ValueError:
            raise ValueError("Invalid checkpoint identifier") from None
        checkpoint = db.session.get(EvidenceCheckpoint, checkpoint_id)
        if checkpoint is None or checkpoint.retention_id != aggregate:
            raise ValueError("Checkpoint not found for retention")
        evidence = {
            "payload": checkpoint.payload, "algorithm": checkpoint.algorithm,
            "key_id": checkpoint.key_id, "signature": checkpoint.signature,
        }
        trusted = trusted_checkpoint_key(current_app.config, checkpoint.key_id)
        if not verify_checkpoint(evidence, trusted):
            raise ValueError("Checkpoint cryptographic verification failed")
    else:
        raise ValueError("Unknown preservation event")


def _verify_timestamp_event(payload, key):
    from app.models.evidence_timestamp import EvidenceTimestamp
    from app.services.rfc3161_timestamp import decode_token, verify_timestamp
    from flask import current_app
    retention_id = payload.get("aggregate_id")
    if type(retention_id) is not int or not key.startswith("evidence-timestamp:"):
        raise ValueError("Invalid timestamp event")
    try:
        token_id = int(key.rsplit(":", 1)[-1])
    except ValueError:
        raise ValueError("Invalid timestamp identifier") from None
    item = db.session.get(EvidenceTimestamp, token_id)
    if item is None or item.retention_id != retention_id:
        raise ValueError("Timestamp does not match retained artifact")
    verified = verify_timestamp(
        decode_token(item.token_der_b64), item.artifact_sha256,
        current_app.config,
    )
    if (verified["token_sha256"] != item.token_sha256
            or verified["tsa_certificate_sha256"] != item.tsa_certificate_sha256
            or verified["gen_time"] != item.gen_time):
        raise ValueError("Timestamp immutable evidence mismatch")


def _verify_crl_event(payload, key):
    from app.models.certificate_revocation import CertificateRevocationEvidence
    from app.models.evidence_timestamp import EvidenceTimestamp
    from app.models.evidence_preservation import EvidenceRetention
    from app.services.certificate_revocation import verify_snapshot, _read_pem
    from flask import current_app
    if not key.startswith("evidence-crl:") or type(payload.get("aggregate_id")) is not int:
        raise ValueError("Invalid CRL event")
    try:
        evidence_id = int(key.rsplit(":", 1)[-1])
    except ValueError:
        raise ValueError("Invalid CRL event identifier") from None
    record = db.session.get(CertificateRevocationEvidence, evidence_id)
    if record is None:
        raise ValueError("CRL evidence missing")
    timestamp = db.session.get(EvidenceTimestamp, record.timestamp_id)
    retention = db.session.get(EvidenceRetention, timestamp.retention_id) if timestamp else None
    if (timestamp is None or retention is None
            or retention.id != payload["aggregate_id"]
            or timestamp.organization_id != record.organization_id
            or retention.organization_id != record.organization_id
            or timestamp.tsa_certificate_sha256 != record.subject_certificate_sha256):
        raise ValueError("CRL evidence organizational or certificate mismatch")
    root = _read_pem(current_app.config.get("RFC3161_TRUST_ROOT_PEM"), "Trusted TSA root")
    verify_snapshot(record, root)


HANDLERS = {
    "document.draft.created": _verify_document_event,
    "document.draft.updated": _verify_document_event,
    "document.draft.deleted": _verify_document_event,
    "document.snapshot.created": _verify_document_event,
    "document.file.ingested": _verify_document_event,
    "envelope.draft.created": _verify_envelope_event,
    "envelope.prepared": _verify_envelope_event,
    "envelope.cancelled": _verify_envelope_event,
    "envelope.review.acknowledged": _verify_signer_review,
    "envelope.review.declined": _verify_signer_review,
    "review.receipt.issued": _verify_review_receipt_event,
    "platform.pdf.sealed": _verify_pdf_seal_event,
    "signer.key.registered": _verify_signer_crypto_event,
    "signer.key.revoked": _verify_signer_crypto_event,
    "signer.document.endorsed": _verify_signer_crypto_event,
    "stamp.registration.requested": _verify_stamp_custody_event,
    "stamp.registration.approved": _verify_stamp_custody_event,
    "stamp.registration.revoked": _verify_stamp_custody_event,
    "stamp.use.requested": _verify_stamp_custody_event,
    "stamp.use.approved": _verify_stamp_custody_event,
    "stamp.use.rejected": _verify_stamp_custody_event,
    "stamp.attestation.issued": _verify_stamp_custody_event,
    "stamp.pdf.issued": _verify_stamp_custody_event,
    "stamp.design.proposed": _verify_stamp_design_event,
    "stamp.design.approved": _verify_stamp_design_event,
    "stamp.design.rejected": _verify_stamp_design_event,
    "evidence.retention.registered": _verify_preservation_event,
    "evidence.hold.placed": _verify_preservation_event,
    "evidence.hold.released": _verify_preservation_event,
    "evidence.checkpoint.issued": _verify_preservation_event,
    "evidence.timestamp.issued": _verify_timestamp_event,
    "evidence.crl.captured": _verify_crl_event,
}


@outbox_cli.command("status")
@with_appcontext
def status():
    """Print queue status, without exposing event payloads."""
    from sqlalchemy import func
    rows = db.session.query(OutboxEvent.state, func.count(OutboxEvent.id)).group_by(
        OutboxEvent.state
    ).all()
    for state, count in rows:
        click.echo("%s: %s" % (state, count))


@outbox_cli.command("drain")
@click.option("--limit", default=25, type=click.IntRange(1, 1000))
@with_appcontext
def drain(limit):
    """Consume a bounded number of due events; run repeatedly via supervisor."""
    processed = 0
    for _ in range(limit):
        if not deliver_one(HANDLERS):
            break
        processed += 1
    click.echo("Processed %s event attempt(s)" % processed)


@outbox_cli.command("retry-dead")
@click.argument("event_id", type=int)
@click.option("--confirm", is_flag=True, required=True, help="Explicitly approve one dead-letter retry")
@with_appcontext
def retry_dead(event_id, confirm):
    """Manually retry a single dead event after investigating its failure."""
    from datetime import datetime
    item = db.session.query(OutboxEvent).filter_by(
        id=event_id, state="dead"
    ).with_for_update().first()
    if item is None:
        raise click.ClickException("Dead-letter item not found")
    if item.event_type not in HANDLERS:
        raise click.ClickException("Handler not registered; retry refused")
    item.state = "pending"
    item.attempts = 0
    item.next_attempt_at = datetime.utcnow()
    item.locked_until = None
    item.lease_token = None
    item.last_error = None
    db.session.commit()
    click.echo("Retry queued for event %s" % event_id)
