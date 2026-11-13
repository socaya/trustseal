"""Operator-controlled TSA certificate CRL observation, with no network fetch.

CRL is supplied from a preapproved operator-managed path. No application
account can upload arbitrary issuer certificates or select trust anchors.
"""
import base64
from datetime import datetime

import click
from flask import current_app
from flask.cli import AppGroup, with_appcontext
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.evidence_timestamp import EvidenceTimestamp
from app.models.evidence_preservation import EvidenceRetention
from app.models.certificate_revocation import CertificateRevocationEvidence
from app.cli.preservation import _operator
from app.services.event_delivery import enqueue
from app.services.certificate_revocation import (
    RevocationEvidenceError, _read_pem, validate_crl, verify_snapshot, MAX_CRL,
)
from app.services.rfc3161_timestamp import decode_token, verify_timestamp


revocation_cli = AppGroup("revocation")


def _trusted_crl(config):
    path = config.get("CRL_EVIDENCE_DER")
    if not isinstance(path, str) or not __import__("os").path.isabs(path):
        raise RevocationEvidenceError("Approved CRL DER path not configured")
    from pathlib import Path
    file = Path(path)
    if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_CRL:
        raise RevocationEvidenceError("Approved CRL unavailable")
    return file.read_bytes()


@revocation_cli.command("capture")
@click.argument("timestamp_id", type=int)
@with_appcontext
def capture(timestamp_id):
    if not current_app.config.get("CRL_EVIDENCE_ENABLED", False):
        raise click.ClickException("CRL observation is disabled")
    timestamp = EvidenceTimestamp.query.filter_by(id=timestamp_id).with_for_update().first()
    retention = db.session.get(EvidenceRetention, timestamp.retention_id) if timestamp else None
    if timestamp is None or retention is None:
        raise click.ClickException("Retained timestamp unavailable")
    try:
        operator = _operator(retention)
        if (timestamp.organization_id != retention.organization_id
                or timestamp.artifact_sha256 != retention.artifact_sha256):
            raise RevocationEvidenceError("Timestamp/retention context mismatch")
        verified_token = verify_timestamp(
            decode_token(timestamp.token_der_b64), timestamp.artifact_sha256,
            current_app.config,
        )
        if (verified_token["token_sha256"] != timestamp.token_sha256
                or verified_token["tsa_certificate_sha256"] != timestamp.tsa_certificate_sha256
                or verified_token["gen_time"] != timestamp.gen_time):
            raise RevocationEvidenceError("Timestamp token verification mismatch")
        subject = _read_pem(current_app.config.get("RFC3161_TSA_CERT_PEM"), "TSA signer")
        issuer = _read_pem(current_app.config.get("CRL_ISSUER_CERT_PEM"), "CRL issuer")
        root = _read_pem(current_app.config.get("RFC3161_TRUST_ROOT_PEM"), "Trusted TSA root")
        crl = _trusted_crl(current_app.config)
        at = datetime.utcnow()
        result = validate_crl(crl, subject, issuer, root, observed_at=at)
        if result["subject_certificate_sha256"] != timestamp.tsa_certificate_sha256:
            raise RevocationEvidenceError("CRL signer differs from retained TSA")
        if result["status"] != "good":
            raise RevocationEvidenceError("TSA signer listed as revoked")
        certificate = x509.load_pem_x509_certificate(subject)
        issuer_cert = x509.load_pem_x509_certificate(issuer)
        evidence = CertificateRevocationEvidence(
            organization_id=retention.organization_id,
            timestamp_id=timestamp.id,
            operator_id=operator.id,
            subject_certificate_sha256=result["subject_certificate_sha256"],
            issuer_certificate_sha256=result["issuer_certificate_sha256"],
            crl_sha256=result["crl_sha256"],
            crl_der_b64=base64.b64encode(crl).decode("ascii"),
            subject_der_b64=base64.b64encode(
                certificate.public_bytes(serialization.Encoding.DER)
            ).decode("ascii"),
            issuer_der_b64=base64.b64encode(
                issuer_cert.public_bytes(serialization.Encoding.DER)
            ).decode("ascii"),
            this_update=result["this_update"],
            next_update=result["next_update"],
            status=result["status"],
            checked_at=result["checked_at"],
        )
        db.session.add(evidence)
        db.session.flush()
        enqueue(
            event_type="evidence.crl.captured",
            aggregate_type="evidence_retention",
            aggregate_id=retention.id,
            organization_id=retention.organization_id,
            actor_id=operator.id,
            action="evidence.crl.captured",
            idempotency_key="evidence-crl:%s" % evidence.id,
        )
        db.session.commit()
    except (RevocationEvidenceError, OSError, ValueError, TypeError, IntegrityError):
        db.session.rollback()
        raise click.ClickException("Revocation evidence capture verification failed") from None
    click.echo("Validated and retained TSA CRL evidence: %s" % evidence.id)


@revocation_cli.command("verify")
@click.argument("evidence_id", type=int)
@with_appcontext
def verify(evidence_id):
    record = db.session.get(CertificateRevocationEvidence, evidence_id)
    if record is None:
        raise click.ClickException("CRL record unavailable")
    timestamp = db.session.get(EvidenceTimestamp, record.timestamp_id)
    if timestamp is None or timestamp.organization_id != record.organization_id:
        raise click.ClickException("CRL timestamp context unavailable")
    try:
        root = _read_pem(current_app.config.get("RFC3161_TRUST_ROOT_PEM"), "Trusted TSA root")
        result = verify_snapshot(record, root)
        token = verify_timestamp(
            decode_token(timestamp.token_der_b64), timestamp.artifact_sha256,
            current_app.config,
        )
        if (result["subject_certificate_sha256"] != timestamp.tsa_certificate_sha256
                or token["tsa_certificate_sha256"] != timestamp.tsa_certificate_sha256
                or token["token_sha256"] != timestamp.token_sha256
                or token["gen_time"] != timestamp.gen_time):
            raise RevocationEvidenceError("CRL not bound to verified TSA token")
    except (RevocationEvidenceError, ValueError, OSError):
        raise click.ClickException("CRL snapshot integrity verification failed") from None
    click.echo("Historical CRL observation verified: %s" % record.id)
