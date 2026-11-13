"""Operator-only signed evidence integrity checkpoint creation and verification."""
from datetime import datetime

import click
from flask import current_app
from flask.cli import AppGroup, with_appcontext

from app.extensions import db
from app.models.user import User
from app.models.evidence_preservation import EvidenceRetention, EvidenceCheckpoint
from app.policies.api_access import is_admin
from app.services.signing_receipts import load_private_key
from app.services.event_delivery import enqueue
from app.services.evidence_preservation import (
    artifact_for, verify_artifact, checkpoint_payload, sign_checkpoint,
    verify_checkpoint, trusted_checkpoint_key,
)

preservation_cli = AppGroup("preservation")


def _operator(retention):
    configured = current_app.config.get("EVIDENCE_CHECKPOINT_OPERATOR_ID")
    if configured is None or not str(configured).isdecimal():
        raise ValueError("Checkpoint operator not configured")
    actor = db.session.get(User, int(configured))
    if (actor is None or not actor.is_active or not is_admin(actor.id)
            or actor.organization_id != retention.organization_id
            or actor.id == retention.created_by_id):
        raise ValueError("Independent administrator required")
    return actor


@preservation_cli.command("checkpoint")
@click.argument("retention_id", type=int)
@with_appcontext
def create_checkpoint(retention_id):
    """Reverify retained PDF and issue a signed detached observation."""
    if not current_app.config.get("EVIDENCE_CHECKPOINT_ENABLED", False):
        raise click.ClickException("Integrity checkpoint issuance is disabled")
    retention = db.session.query(EvidenceRetention).filter_by(
        id=retention_id
    ).with_for_update().first()
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
            raise ValueError("Retained source digest mismatch")
        checked_at = datetime.utcnow()
        payload = checkpoint_payload(retention, operator.id, checked_at)
        private = load_private_key(
            current_app.config.get("EVIDENCE_CHECKPOINT_PRIVATE_KEY")
        )
        proof = sign_checkpoint(payload, private)
        trusted = trusted_checkpoint_key(current_app.config, proof["key_id"])
        if not verify_checkpoint(proof, trusted):
            raise ValueError("Checkpoint signing verification failed")
        item = EvidenceCheckpoint(
            retention_id=retention.id,
            organization_id=retention.organization_id,
            operator_id=operator.id, payload=payload,
            signature=proof["signature"], algorithm=proof["algorithm"],
            key_id=proof["key_id"], created_at=checked_at,
        )
        db.session.add(item)
        db.session.flush()
        enqueue(
            event_type="evidence.checkpoint.issued",
            aggregate_type="evidence_retention", aggregate_id=retention.id,
            organization_id=retention.organization_id,
            actor_id=operator.id, action="evidence.checkpoint.issued",
            idempotency_key="evidence-checkpoint:%s" % item.id,
        )
        db.session.commit()
    except (ValueError, OSError, TypeError, KeyError):
        db.session.rollback()
        raise click.ClickException("Integrity checkpoint prerequisites failed") from None
    click.echo("Issued signed evidence checkpoint: %s" % item.id)


@preservation_cli.command("verify")
@click.argument("checkpoint_id", type=int)
@with_appcontext
def verify_checkpoint_cli(checkpoint_id):
    item = db.session.get(EvidenceCheckpoint, checkpoint_id)
    if item is None:
        raise click.ClickException("Checkpoint missing")
    retention = db.session.get(EvidenceRetention, item.retention_id)
    if retention is None:
        raise click.ClickException("Retention record missing")
    try:
        expected = checkpoint_payload(
            retention, item.operator_id, item.created_at
        )
        if (expected != item.payload
                or item.organization_id != retention.organization_id):
            raise ValueError("Checkpoint evidence inconsistent")
        key = trusted_checkpoint_key(current_app.config, item.key_id)
        proof = {
            "payload": item.payload, "algorithm": item.algorithm,
            "key_id": item.key_id, "signature": item.signature,
        }
        if not verify_checkpoint(proof, key):
            raise ValueError("Signature invalid")
        artifact = artifact_for(
            retention.artifact_type, retention.artifact_id,
            retention.organization_id,
        )
        if verify_artifact(
            artifact, retention.artifact_type, current_app.config
        ) != retention.artifact_sha256:
            raise ValueError("Current bytes do not match recorded observation")
    except (ValueError, OSError, TypeError, KeyError):
        raise click.ClickException("Checkpoint or retained artifact failed verification") from None
    click.echo("Checkpoint signature and current PDF validated: %s" % item.id)
