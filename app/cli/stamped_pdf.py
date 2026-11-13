"""Operator-controlled visible stamp derivative from a frozen unsigned PDF.

The existing signed PDF is never edited. The approved stamp attestation
anchors a new derivative, which is CMS-signed *after* the imprint is rendered.
"""
import io
import hashlib

import click
from flask import current_app
from flask.cli import AppGroup, with_appcontext
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.documents.document_blob import DocumentBlob
from app.models.pdf_finalization import FinalizedPdf
from app.models.stamped_pdf import StampedPdf
from app.models.stamp_design import StampDesignVersion
from app.services.stamp_designs import checked_design
from app.models.stamp_custody import ManagedStamp, StampApplication, StampAttestation
from app.services.documents.private_storage import (
    check_object_digest, store_scanned_pdf, cleanup_object, IngestionError,
)
from app.services.platform_pdf_seal import seal_pdf, inspect_signed_pdf, PdfFinalizationError
from app.services.stamp_attestation import (
    stamp_payload, verify_attestation, trusted_stamp_key, attestation_digest,
)
from app.services.stamp_pdf_provenance import build_stamp_provenance, provenance_sha256
from app.services.stamp_pdf_impression import render_stamped_source
from app.services.event_delivery import enqueue
from app.cli.stamp_custody import _operator, _verify_pdf

stamped_pdf_cli = AppGroup("stamped-pdf")


def provenance_for(record, application, stamp, attestation, pdf, original):
    return build_stamp_provenance(
        source_pdf_sha256=pdf.output_sha256,
        unsigned_pdf_sha256=original.sha256,
        signed_review_sha256=pdf.evidence_sha256,
        stamp_receipt_sha256=attestation_digest({
            "payload": attestation.payload, "algorithm": attestation.algorithm,
            "key_id": attestation.key_id, "signature": attestation.signature,
        }),
        stamp_attestation_id=attestation.id,
        stamp_code=stamp.code,
        page_number=record.page_number,
        x_pt=record.x_pt,
        y_pt=record.y_pt,
    )


def checked_stamped_pdf(record, config):
    if (not record or not record.signed_evidence_sha256):
        raise PdfFinalizationError("Stamped PDF manifest incomplete")
    path = check_object_digest(record.object_key, record.output_sha256, config)
    result = inspect_signed_pdf(
        path.read_bytes(), config,
        expected_evidence_sha256=record.signed_evidence_sha256,
        expected_certificate_sha256=record.certificate_sha256,
        evidence_purpose="stamp",
    )
    if not result["overall_valid"]:
        raise PdfFinalizationError("Stamped PDF CMS signature invalid")
    return path


@stamped_pdf_cli.command("issue")
@click.argument("attestation_id", type=int)
@click.option("--page", type=int, required=True)
@click.option("--x", "x_pt", type=int, required=True)
@click.option("--y", "y_pt", type=int, required=True)
@click.option("--design-id", type=int, default=None, help="Approved stamp design version ID")
@with_appcontext
def issue_stamped_pdf(attestation_id, page, x_pt, y_pt, design_id):
    """Create one approved visible impression and seal a NEW PDF derivative."""
    if (not current_app.config.get("STAMP_PDF_RENDER_ENABLED", False)
            or not current_app.config.get("PDF_FINALIZATION_ENABLED", False)):
        raise click.ClickException("Visible stamped PDF issuance is disabled")
    receipt = StampAttestation.query.filter_by(id=attestation_id).with_for_update().first()
    if receipt is None:
        raise click.ClickException("Stamp attestation unavailable")
    existing = StampedPdf.query.filter_by(stamp_attestation_id=receipt.id).first()
    if existing:
        db.session.rollback()
        click.echo("Stamped PDF already exists: %s" % existing.id)
        return
    application = db.session.get(StampApplication, receipt.application_id)
    stamp = ManagedStamp.query.filter_by(
        id=receipt.stamp_id, organization_id=receipt.organization_id
    ).with_for_update().first()
    pdf = db.session.get(
        FinalizedPdf, application.finalized_pdf_id
    ) if application is not None else None
    object_key = None
    try:
        if (stamp is None or application is None or pdf is None
                or stamp.status != "active"
                or application.status != "approved"
                or application.stamp_id != stamp.id
                or application.organization_id != stamp.organization_id
                or application.source_sha256 != pdf.output_sha256
                or application.evidence_sha256 != pdf.evidence_sha256
                or pdf.organization_id != stamp.organization_id
                or receipt.organization_id != stamp.organization_id):
            raise ValueError("Stamp authorization or finalized source is invalid")
        operator = _operator(stamp, application)
        _verify_pdf(pdf)
        trusted = trusted_stamp_key(current_app.config, receipt.key_id)
        signed_receipt = {
            "payload": receipt.payload,
            "algorithm": receipt.algorithm,
            "key_id": receipt.key_id,
            "signature": receipt.signature,
        }
        expected_receipt = stamp_payload(
            stamp, application, pdf, receipt.operator_id, receipt.created_at
        )
        if (receipt.payload != expected_receipt
                or not verify_attestation(signed_receipt, trusted)):
            raise ValueError("Stamp attestation signature or binding invalid")
        source_blob = db.session.get(DocumentBlob, pdf.source_blob_id)
        if source_blob is None or source_blob.sha256 != pdf.source_sha256:
            raise ValueError("Original unsigned source manifest mismatch")
        original = check_object_digest(
            source_blob.object_key, source_blob.sha256, current_app.config
        ).read_bytes()
        design = None
        layout = None
        logo = None
        if design_id is not None:
            design = StampDesignVersion.query.filter_by(
                id=design_id, stamp_id=stamp.id,
                organization_id=stamp.organization_id, state="approved",
            ).first()
            if design is None:
                raise ValueError("Approved design version is required")
            layout, logo = checked_design(design)
        rendered = render_stamped_source(
            original, stamp_code=stamp.code, stamp_name=stamp.name,
            attestation_id=receipt.id, page_number=page, x_pt=x_pt, y_pt=y_pt,
            layout=layout, logo_png=logo,
        )
        provenance = build_stamp_provenance(
            source_pdf_sha256=pdf.output_sha256,
            unsigned_pdf_sha256=source_blob.sha256,
            signed_review_sha256=pdf.evidence_sha256,
            stamp_receipt_sha256=attestation_digest(signed_receipt),
            stamp_attestation_id=receipt.id,
            stamp_code=stamp.code,
            page_number=page, x_pt=x_pt, y_pt=y_pt,
            design_version_id=design.id if design else None,
            design_sha256=design.design_sha256 if design else None,
        )
        bound_digest = provenance_sha256(provenance)
        sealed, cert_fingerprint, _status = seal_pdf(
            rendered, current_app.config, bound_digest, evidence_purpose="stamp"
        )
        object_key, _filename, size, digest, _scanner = store_scanned_pdf(
            io.BytesIO(sealed),
            "TrustSeal-visible-stamp-%s.pdf" % receipt.id, current_app.config,
        )
        record = StampedPdf(
            organization_id=stamp.organization_id,
            stamp_attestation_id=receipt.id,
            design_version_id=design.id if design else None,
            design_sha256=design.design_sha256 if design else None,
            source_finalized_pdf_id=pdf.id,
            source_finalized_sha256=pdf.output_sha256,
            original_document_sha256=source_blob.sha256,
            stamp_evidence_sha256=provenance["stamp_attestation_sha256"],
            signed_evidence_sha256=bound_digest,
            object_key=object_key, output_sha256=digest, output_size=size,
            certificate_sha256=cert_fingerprint,
            page_number=page, x_pt=x_pt, y_pt=y_pt,
            issued_by_id=operator.id,
        )
        db.session.add(record)
        db.session.flush()
        enqueue(
            event_type="stamp.pdf.issued", aggregate_type="stamp_application",
            aggregate_id=application.id, organization_id=stamp.organization_id,
            actor_id=operator.id, action="stamp.pdf.issued",
            idempotency_key="stamp-pdf:%s" % receipt.id,
        )
        db.session.commit()
    except (ValueError, TypeError, OSError, IntegrityError,
            IngestionError, PdfFinalizationError):
        db.session.rollback()
        if object_key:
            try:
                cleanup_object(object_key, current_app.config)
            except Exception:
                current_app.logger.exception("Failed to clear orphan stamped PDF")
        raise click.ClickException("Visible stamp issuance prerequisites failed") from None
    click.echo("Created CMS-sealed stamped PDF derivative: %s" % record.id)


@stamped_pdf_cli.command("verify")
@click.argument("artifact_id", type=int)
@with_appcontext
def verify_stamped_pdf(artifact_id):
    record = db.session.get(StampedPdf, artifact_id)
    if record is None:
        raise click.ClickException("Stamped PDF not found")
    # Verify the original signed artifact and entire approval/provenance chain,
    # not only the newly signed output CMS.
    from app.blueprints.estamp.stamped_pdf_api import _verify_lineage
    receipt = db.session.get(StampAttestation, record.stamp_attestation_id)
    application = db.session.get(StampApplication, receipt.application_id) if receipt else None
    stamp = db.session.get(ManagedStamp, receipt.stamp_id) if receipt else None
    source = db.session.get(FinalizedPdf, record.source_finalized_pdf_id)
    if any(item is None for item in (receipt, application, stamp, source)):
        raise click.ClickException("Stamped PDF approval lineage incomplete")
    try:
        _verify_lineage(record, receipt, application, stamp, source)
    except (ValueError, OSError, PdfFinalizationError, IngestionError):
        raise click.ClickException("Stamped PDF lineage verification failed") from None
    click.echo("Stamped PDF and approved provenance valid: %s" % record.id)
