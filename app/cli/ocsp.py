"""Operator-controlled OCSP snapshot capture; never fetch untrusted URLs."""
import base64
from datetime import datetime
from pathlib import Path

import click
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from flask import current_app
from flask.cli import AppGroup, with_appcontext
from sqlalchemy.exc import IntegrityError

from app.cli.preservation import _operator
from app.extensions import db
from app.models.evidence_preservation import EvidenceRetention
from app.models.evidence_timestamp import EvidenceTimestamp
from app.models.ocsp_evidence import OcspEvidence
from app.services.certificate_revocation import _read_pem
from app.services.event_delivery import enqueue
from app.services.ocsp_evidence import (
    MAX_OCSP, OcspEvidenceError, validate_ocsp, verify_ocsp_snapshot,
)
from app.services.rfc3161_timestamp import decode_token, verify_timestamp

ocsp_cli = AppGroup("ocsp")


def _approved_response(config):
    name = config.get("OCSP_EVIDENCE_DER")
    if not isinstance(name, str) or not Path(name).is_absolute():
        raise OcspEvidenceError("Approved OCSP response file not configured")
    path = Path(name)
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_OCSP:
        raise OcspEvidenceError("OCSP response unavailable")
    return path.read_bytes()


@ocsp_cli.command("capture")
@click.argument("timestamp_id", type=int)
@with_appcontext
def capture(timestamp_id):
    if not current_app.config.get("OCSP_EVIDENCE_ENABLED", False):
        raise click.ClickException("OCSP evidence collection disabled")
    token = EvidenceTimestamp.query.filter_by(id=timestamp_id).with_for_update().first()
    retention = db.session.get(EvidenceRetention, token.retention_id) if token else None
    if token is None or retention is None:
        raise click.ClickException("Retained TSA token not found")
    try:
        operator = _operator(retention)
        if (token.organization_id != retention.organization_id
                or token.artifact_sha256 != retention.artifact_sha256):
            raise OcspEvidenceError("TSA token not bound to retention")
        verified = verify_timestamp(
            decode_token(token.token_der_b64), token.artifact_sha256,
            current_app.config,
        )
        if (verified["tsa_certificate_sha256"] != token.tsa_certificate_sha256
                or verified["token_sha256"] != token.token_sha256
                or verified["gen_time"] != token.gen_time):
            raise OcspEvidenceError("TSA signature proof inconsistent")
        subject = _read_pem(current_app.config.get("RFC3161_TSA_CERT_PEM"), "TSA signer")
        issuer = _read_pem(current_app.config.get("OCSP_ISSUER_CERT_PEM"), "OCSP issuer")
        root = _read_pem(current_app.config.get("RFC3161_TRUST_ROOT_PEM"), "TSA trust root")
        response = _approved_response(current_app.config)
        result = validate_ocsp(response, subject, issuer, root, observed_at=datetime.utcnow())
        if (result["status"] != "good"
                or result["subject_certificate_sha256"] != token.tsa_certificate_sha256):
            raise OcspEvidenceError("TSA signer status not verified good")
        item = OcspEvidence(
            organization_id=retention.organization_id, timestamp_id=token.id,
            operator_id=operator.id,
            subject_certificate_sha256=result["subject_certificate_sha256"],
            issuer_certificate_sha256=result["issuer_certificate_sha256"],
            response_sha256=result["response_sha256"],
            response_der_b64=base64.b64encode(response).decode(),
            subject_der_b64=base64.b64encode(
                x509.load_pem_x509_certificate(subject).public_bytes(serialization.Encoding.DER)
            ).decode(),
            issuer_der_b64=base64.b64encode(
                x509.load_pem_x509_certificate(issuer).public_bytes(serialization.Encoding.DER)
            ).decode(),
            produced_at=result["produced_at"],
            this_update=result["this_update"], next_update=result["next_update"],
            checked_at=result["checked_at"], status=result["status"],
        )
        db.session.add(item)
        db.session.flush()
        enqueue(
            event_type="evidence.ocsp.captured",
            aggregate_type="evidence_retention",
            aggregate_id=retention.id,
            organization_id=retention.organization_id,
            actor_id=operator.id,
            action="evidence.ocsp.captured",
            idempotency_key="evidence-ocsp:%s" % item.id,
        )
        db.session.commit()
    except (ValueError, OSError, TypeError, IntegrityError):
        db.session.rollback()
        raise click.ClickException("OCSP capture prerequisites failed") from None
    click.echo("Captured verified OCSP observation: %s" % item.id)


@ocsp_cli.command("verify")
@click.argument("evidence_id", type=int)
@with_appcontext
def verify(evidence_id):
    item = db.session.get(OcspEvidence, evidence_id)
    token = db.session.get(EvidenceTimestamp, item.timestamp_id) if item else None
    retention = db.session.get(EvidenceRetention, token.retention_id) if token else None
    if item is None or token is None or retention is None:
        raise click.ClickException("OCSP evidence unavailable")
    try:
        if (item.organization_id != token.organization_id
                or token.organization_id != retention.organization_id):
            raise OcspEvidenceError("OCSP tenant mismatch")
        root = _read_pem(current_app.config.get("RFC3161_TRUST_ROOT_PEM"), "Trust root")
        status = verify_ocsp_snapshot(item, root)
        proof = verify_timestamp(
            decode_token(token.token_der_b64), token.artifact_sha256,
            current_app.config,
        )
        if (status["subject_certificate_sha256"] != token.tsa_certificate_sha256
                or proof["token_sha256"] != token.token_sha256
                or proof["gen_time"] != token.gen_time
                or proof["tsa_certificate_sha256"] != token.tsa_certificate_sha256):
            raise OcspEvidenceError("OCSP status not bound to TSA timestamp")
    except (ValueError, OSError, TypeError):
        raise click.ClickException("OCSP snapshot validation failed") from None
    click.echo("OCSP observation signature and TSA binding valid: %s" % item.id)
