"""Operator creates immutable, deliberately partial validation dossiers."""
import click
from flask import current_app
from flask.cli import AppGroup, with_appcontext
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.cli.preservation import _operator
from app.models.evidence_preservation import EvidenceRetention
from app.models.evidence_timestamp import EvidenceTimestamp
from app.models.certificate_revocation import CertificateRevocationEvidence
from app.models.ocsp_evidence import OcspEvidence
from app.models.validation_dossier import ValidationDossier
from app.services.validation_dossier import (
    build_dossier, verify_dossier, digest_manifest,
)
from app.services.event_delivery import enqueue

dossier_cli = AppGroup("validation-dossier")


def _sources(timestamp):
    ocsp = OcspEvidence.query.filter_by(
        timestamp_id=timestamp.id, organization_id=timestamp.organization_id
    ).order_by(OcspEvidence.id).limit(101).all()
    crl = CertificateRevocationEvidence.query.filter_by(
        timestamp_id=timestamp.id, organization_id=timestamp.organization_id
    ).order_by(CertificateRevocationEvidence.id).limit(101).all()
    return ocsp, crl


@dossier_cli.command("issue")
@click.argument("timestamp_id", type=int)
@with_appcontext
def issue(timestamp_id):
    if not current_app.config.get("VALIDATION_DOSSIER_ENABLED", False):
        raise click.ClickException("Validation dossier issuance disabled")
    timestamp = EvidenceTimestamp.query.filter_by(id=timestamp_id).with_for_update().first()
    retention = db.session.get(EvidenceRetention, timestamp.retention_id) if timestamp else None
    if timestamp is None or retention is None:
        raise click.ClickException("Retained timestamp unavailable")
    try:
        operator = _operator(retention)
        ocsp, crl = _sources(timestamp)
        manifest = build_dossier(
            retention, timestamp, ocsp, crl, current_app.config
        )
        digest = digest_manifest(manifest)
        item = ValidationDossier(
            retention_id=retention.id, organization_id=retention.organization_id,
            timestamp_id=timestamp.id, operator_id=operator.id,
            manifest=manifest, manifest_sha256=digest,
        )
        db.session.add(item)
        db.session.flush()
        enqueue(
            event_type="evidence.dossier.issued",
            aggregate_type="evidence_retention", aggregate_id=retention.id,
            organization_id=retention.organization_id, actor_id=operator.id,
            action="evidence.dossier.issued",
            idempotency_key="evidence-dossier:%s" % item.id,
        )
        db.session.commit()
    except (ValueError, OSError, TypeError, IntegrityError):
        db.session.rollback()
        raise click.ClickException("Validation dossier prerequisites failed") from None
    click.echo("Issued partial validation evidence dossier: %s" % item.id)


@dossier_cli.command("verify")
@click.argument("dossier_id", type=int)
@with_appcontext
def verify(dossier_id):
    item = db.session.get(ValidationDossier, dossier_id)
    timestamp = db.session.get(EvidenceTimestamp, item.timestamp_id) if item else None
    retention = db.session.get(EvidenceRetention, item.retention_id) if item else None
    if any(row is None for row in (item, timestamp, retention)):
        raise click.ClickException("Dossier chain unavailable")
    try:
        ocsp, crl = _sources(timestamp)
        verify_dossier(item, retention, timestamp, ocsp, crl, current_app.config)
    except (ValueError, OSError, TypeError):
        raise click.ClickException("Dossier source or cryptographic evidence invalid") from None
    click.echo("Partial dossier source validation succeeded: %s" % item.id)
