"""Issue a separate DSS-bearing PDF derivative from an approved partial dossier.

A DSS-only derivative is never reclassified as PAdES-LT or PAdES-LTA.
The original immutable platform-signed source object remains unchanged.
"""
import hashlib
import io

import click
from flask import current_app
from flask.cli import AppGroup, with_appcontext
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.pdf_dss_derivative import PdfDssDerivative
from app.models.validation_dossier import ValidationDossier
from app.models.evidence_preservation import EvidenceRetention
from app.models.evidence_timestamp import EvidenceTimestamp
from app.models.ocsp_evidence import OcspEvidence
from app.models.certificate_revocation import CertificateRevocationEvidence
from app.cli.preservation import _operator
from app.services.evidence_preservation import artifact_for, verify_artifact
from app.services.validation_dossier import verify_dossier
from app.services.documents.private_storage import (
    check_object_digest, store_scanned_pdf, cleanup_object,
)
from app.services.pdf_dss import append_dss_derivative, verify_dss_derivative
from app.services.event_delivery import enqueue

dss_cli = AppGroup("pdf-dss")


def dossier_sources(dossier, token):
    refs = dossier.manifest.get("revocation_observations", [])
    if not isinstance(refs, list) or len(refs) > 200:
        raise ValueError("Invalid dossier evidence")
    ocsp_ids, crl_ids = set(), set()
    for ref in refs:
        if not isinstance(ref, dict) or type(ref.get("id")) is not int:
            raise ValueError("Invalid dossier evidence reference")
        if ref.get("type") == "ocsp":
            ocsp_ids.add(ref["id"])
        elif ref.get("type") == "crl":
            crl_ids.add(ref["id"])
        else:
            raise ValueError("Unknown dossier evidence kind")
    ocsps = OcspEvidence.query.filter(
        OcspEvidence.timestamp_id == token.id,
        OcspEvidence.organization_id == token.organization_id,
        OcspEvidence.id.in_(ocsp_ids),
    ).all() if ocsp_ids else []
    crls = CertificateRevocationEvidence.query.filter(
        CertificateRevocationEvidence.timestamp_id == token.id,
        CertificateRevocationEvidence.organization_id == token.organization_id,
        CertificateRevocationEvidence.id.in_(crl_ids),
    ).all() if crl_ids else []
    if len(ocsps) != len(ocsp_ids) or len(crls) != len(crl_ids):
        raise ValueError("Referenced certificate-status evidence missing")
    return ocsps, crls


def verified_dossier(dossier, config):
    retention = db.session.get(EvidenceRetention, dossier.retention_id)
    token = db.session.get(EvidenceTimestamp, dossier.timestamp_id)
    if (retention is None or token is None
            or retention.organization_id != dossier.organization_id
            or token.organization_id != dossier.organization_id
            or token.retention_id != retention.id):
        raise ValueError("DSS dossier retention binding invalid")
    ocsps, crls = dossier_sources(dossier, token)
    verify_dossier(dossier, retention, token, ocsps, crls, config)
    if "certificate_chain" not in dossier.manifest:
        raise ValueError("DSS requires a pinned certificate-chain dossier")
    return retention, ocsps, crls


def source_attributes(retention, config):
    record = artifact_for(
        retention.artifact_type, retention.artifact_id,
        retention.organization_id,
    )
    if (record.output_sha256 != retention.artifact_sha256
            or verify_artifact(record, retention.artifact_type, config)
            != retention.artifact_sha256):
        raise ValueError("Original PDF source verification failed")
    path = check_object_digest(record.object_key, retention.artifact_sha256, config)
    purpose = "review" if retention.artifact_type == "finalized_pdf" else "stamp"
    evidence = record.evidence_sha256 if purpose == "review" else record.signed_evidence_sha256
    return path.read_bytes(), evidence, record.certificate_sha256, purpose


@dss_cli.command("issue")
@click.argument("dossier_id", type=int)
@with_appcontext
def issue(dossier_id):
    if not current_app.config.get("PDF_DSS_DERIVATIVE_ENABLED", False):
        raise click.ClickException("DSS derivative issuance disabled")
    dossier = ValidationDossier.query.filter_by(id=dossier_id).with_for_update().first()
    if dossier is None:
        raise click.ClickException("Validation dossier not available")
    prior = PdfDssDerivative.query.filter_by(dossier_id=dossier.id).first()
    if prior:
        click.echo("DSS derivative already issued: %s" % prior.id)
        db.session.rollback()
        return
    object_key = None
    try:
        retention, ocsps, crls = verified_dossier(dossier, current_app.config)
        operator = _operator(retention)
        source, evidence, cert, purpose = source_attributes(
            retention, current_app.config,
        )
        derivative = append_dss_derivative(
            source, dossier, ocsps, crls, current_app.config,
            evidence_sha256=evidence, certificate_sha256=cert,
            evidence_purpose=purpose,
        )
        object_key, _name, size, digest, _scanner = store_scanned_pdf(
            io.BytesIO(derivative),
            "TrustSeal-DSS-evidence-%s.pdf" % dossier.id,
            current_app.config,
        )
        record = PdfDssDerivative(
            organization_id=dossier.organization_id,
            retention_id=retention.id,
            dossier_id=dossier.id,
            operator_id=operator.id,
            source_sha256=retention.artifact_sha256,
            dossier_sha256=dossier.manifest_sha256,
            object_key=object_key,
            output_sha256=digest, output_size=size,
            profile="dss_evidence_only_not_pades_lt",
        )
        db.session.add(record)
        db.session.flush()
        enqueue(
            event_type="evidence.dss.issued",
            aggregate_type="evidence_retention",
            aggregate_id=retention.id,
            organization_id=retention.organization_id,
            actor_id=operator.id,
            action="evidence.dss.issued",
            idempotency_key="evidence-dss:%s" % record.id,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        if object_key:
            try:
                cleanup_object(object_key, current_app.config)
            except Exception:
                current_app.logger.exception("Uncommitted DSS output cleanup failed")
        raise click.ClickException("DSS derivative issuance failed") from None
    click.echo("Issued separate non-LT DSS PDF derivative: %s" % record.id)


def checked_derivative(item, config):
    dossier = db.session.get(ValidationDossier, item.dossier_id)
    if dossier is None or dossier.organization_id != item.organization_id:
        raise ValueError("DSS dossier no longer available")
    retention, _ocsps, _crls = verified_dossier(dossier, config)
    if (retention.id != item.retention_id
            or retention.artifact_sha256 != item.source_sha256
            or dossier.manifest_sha256 != item.dossier_sha256
            or item.profile != "dss_evidence_only_not_pades_lt"):
        raise ValueError("DSS immutable manifest inconsistent")
    source, evidence, cert, purpose = source_attributes(retention, config)
    path = check_object_digest(item.object_key, item.output_sha256, config)
    derivative = path.read_bytes()
    if len(derivative) != item.output_size:
        raise ValueError("DSS derivative size mismatch")
    verify_dss_derivative(
        source, derivative, item.output_sha256, config,
        evidence_sha256=evidence, certificate_sha256=cert,
        evidence_purpose=purpose,
    )
    return path


@dss_cli.command("verify")
@click.argument("derivative_id", type=int)
@with_appcontext
def verify(derivative_id):
    item = db.session.get(PdfDssDerivative, derivative_id)
    if item is None:
        raise click.ClickException("DSS derivative missing")
    try:
        checked_derivative(item, current_app.config)
    except Exception:
        raise click.ClickException("DSS derivative verification failed") from None
    click.echo("DSS derivative and original platform seal verified: %s" % item.id)
