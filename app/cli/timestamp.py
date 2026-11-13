"""Operator-controlled detached RFC 3161 timestamp issuance and verification."""
import click
from flask import current_app
from flask.cli import AppGroup, with_appcontext

from app.extensions import db
from app.models.evidence_preservation import EvidenceRetention
from app.models.evidence_timestamp import EvidenceTimestamp
from app.services.event_delivery import enqueue
from app.services.evidence_preservation import artifact_for, verify_artifact
from app.services.rfc3161_timestamp import (
    TimestampError, request_timestamp, verify_timestamp,
    encode_token, decode_token,
)
from app.cli.preservation import _operator

timestamp_cli = AppGroup("timestamp")


@timestamp_cli.command("issue")
@click.argument("retention_id", type=int)
@with_appcontext
def issue(retention_id):
    """Obtain a verifiable detached TSA token for retained exact PDF bytes."""
    if not current_app.config.get("RFC3161_ENABLED", False):
        raise click.ClickException("External timestamp requests are disabled")
    retention = EvidenceRetention.query.filter_by(id=retention_id).with_for_update().first()
    if retention is None:
        raise click.ClickException("Retention record unavailable")
    try:
        operator = _operator(retention)
        artifact = artifact_for(
            retention.artifact_type, retention.artifact_id,
            retention.organization_id,
        )
        if (artifact.output_sha256 != retention.artifact_sha256
                or verify_artifact(artifact, retention.artifact_type, current_app.config)
                != retention.artifact_sha256):
            raise TimestampError("Retention integrity check failed")
        raw, verified = request_timestamp(retention.artifact_sha256, current_app.config)
        receipt = EvidenceTimestamp(
            retention_id=retention.id,
            organization_id=retention.organization_id,
            operator_id=operator.id,
            artifact_sha256=retention.artifact_sha256,
            tsa_certificate_sha256=verified["tsa_certificate_sha256"],
            token_sha256=verified["token_sha256"],
            token_der_b64=encode_token(raw),
            gen_time=verified["gen_time"],
        )
        db.session.add(receipt)
        db.session.flush()
        enqueue(
            event_type="evidence.timestamp.issued",
            aggregate_type="evidence_retention", aggregate_id=retention.id,
            organization_id=retention.organization_id, actor_id=operator.id,
            action="evidence.timestamp.issued",
            idempotency_key="evidence-timestamp:%s" % receipt.id,
        )
        db.session.commit()
    except (ValueError, OSError, TypeError, TimestampError):
        db.session.rollback()
        raise click.ClickException("Trusted timestamp issuance prerequisites failed") from None
    click.echo("Issued and verified detached RFC3161 timestamp: %s" % receipt.id)


@timestamp_cli.command("verify")
@click.argument("timestamp_id", type=int)
@with_appcontext
def verify(timestamp_id):
    record = db.session.get(EvidenceTimestamp, timestamp_id)
    if record is None:
        raise click.ClickException("Timestamp record unavailable")
    retention = db.session.get(EvidenceRetention, record.retention_id)
    try:
        if (retention is None
                or retention.organization_id != record.organization_id
                or retention.artifact_sha256 != record.artifact_sha256):
            raise TimestampError("Timestamp retention binding invalid")
        raw = decode_token(record.token_der_b64)
        result = verify_timestamp(raw, record.artifact_sha256, current_app.config)
        if (result["tsa_certificate_sha256"] != record.tsa_certificate_sha256
                or result["token_sha256"] != record.token_sha256
                or result["gen_time"] != record.gen_time):
            raise TimestampError("Timestamp manifest mismatch")
        artifact = artifact_for(
            retention.artifact_type, retention.artifact_id,
            retention.organization_id,
        )
        if verify_artifact(artifact, retention.artifact_type, current_app.config) != record.artifact_sha256:
            raise TimestampError("Current retained PDF fails integrity verification")
    except (ValueError, OSError, TypeError, TimestampError):
        raise click.ClickException("Timestamp or current retained PDF failed validation") from None
    click.echo("RFC3161 timestamp and current retained PDF validated: %s" % record.id)
