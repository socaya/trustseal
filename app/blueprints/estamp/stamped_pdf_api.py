"""Authorized stamped-PDF download and full lineage verification.

Verification checks independent stamp approval evidence, original signed PDF,
frozen original source hash, signed placement provenance and derivative CMS.
"""
from flask import Blueprint, abort, current_app, jsonify, send_file
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.documents.document_blob import DocumentBlob
from app.models.pdf_finalization import FinalizedPdf
from app.models.stamped_pdf import StampedPdf
from app.models.stamp_design import StampDesignVersion
from app.services.stamp_designs import checked_design
from app.models.stamp_custody import ManagedStamp, StampApplication, StampAttestation
from app.policies.api_access import is_admin
from app.services.token_security import active_token_user
from app.services.documents.private_storage import check_object_digest, IngestionError
from app.services.platform_pdf_seal import inspect_signed_pdf, PdfFinalizationError
from app.services.stamp_attestation import (
    stamp_payload, trusted_stamp_key, verify_attestation, attestation_digest,
)
from app.services.stamp_pdf_provenance import build_stamp_provenance, provenance_sha256
from app.cli.stamped_pdf import checked_stamped_pdf

stamped_pdf_api = Blueprint("stamped_pdf_api", __name__, url_prefix="/api/stamped-pdfs")


def _owned(artifact_id):
    actor = active_token_user()
    if actor is None or not actor.is_active or actor.organization_id is None:
        abort(401)
    artifact = StampedPdf.query.filter_by(
        id=artifact_id, organization_id=actor.organization_id
    ).first()
    if artifact is None:
        abort(404)
    receipt = db.session.get(StampAttestation, artifact.stamp_attestation_id)
    application = db.session.get(StampApplication, receipt.application_id) if receipt else None
    stamp = db.session.get(ManagedStamp, receipt.stamp_id) if receipt else None
    source = db.session.get(FinalizedPdf, artifact.source_finalized_pdf_id)
    if any(item is None for item in (receipt, application, stamp, source)):
        abort(409, description="Stamped PDF provenance incomplete")
    if not all(item.organization_id == actor.organization_id
               for item in (receipt, application, stamp, source)):
        abort(404)
    if not is_admin(actor.id) and actor.id not in (
        application.requested_by_id, stamp.custodian_id,
    ):
        abort(404)
    return artifact, receipt, application, stamp, source


def _verify_lineage(artifact, receipt, application, stamp, source):
    if (receipt.application_id != application.id
            or application.stamp_id != stamp.id
            or application.finalized_pdf_id != source.id
            or artifact.source_finalized_pdf_id != source.id
            or artifact.source_finalized_sha256 != source.output_sha256
            or application.source_sha256 != source.output_sha256
            or artifact.original_document_sha256 != source.source_sha256
            or application.evidence_sha256 != source.evidence_sha256):
        raise ValueError("Stamped source lineage inconsistent")
    frozen = db.session.get(DocumentBlob, source.source_blob_id)
    if frozen is None or frozen.sha256 != artifact.original_document_sha256:
        raise ValueError("Frozen unsigned source manifest unavailable")
    check_object_digest(frozen.object_key, frozen.sha256, current_app.config)
    original_path = check_object_digest(
        source.object_key, source.output_sha256, current_app.config
    )
    original_status = inspect_signed_pdf(
        original_path.read_bytes(), current_app.config,
        expected_evidence_sha256=source.evidence_sha256,
        expected_certificate_sha256=source.certificate_sha256,
    )
    if not original_status["overall_valid"]:
        raise ValueError("Original signed PDF signature invalid")
    expected_receipt = stamp_payload(
        stamp, application, source, receipt.operator_id, receipt.created_at
    )
    signed_receipt = {
        "payload": receipt.payload, "algorithm": receipt.algorithm,
        "key_id": receipt.key_id, "signature": receipt.signature,
    }
    trusted = trusted_stamp_key(current_app.config, receipt.key_id)
    if (receipt.payload != expected_receipt
            or not verify_attestation(signed_receipt, trusted)):
        raise ValueError("Stamp approval signature invalid")
    design = None
    if artifact.design_version_id is not None:
        design = db.session.get(StampDesignVersion, artifact.design_version_id)
        if (design is None or design.state != "approved"
                or design.stamp_id != stamp.id
                or design.organization_id != stamp.organization_id
                or artifact.design_sha256 != design.design_sha256):
            raise ValueError("Approved design identity mismatch")
        checked_design(design)
    elif artifact.design_sha256 is not None:
        raise ValueError("Design hash without version")
    provenance = build_stamp_provenance(
        source_pdf_sha256=source.output_sha256,
        unsigned_pdf_sha256=frozen.sha256,
        signed_review_sha256=source.evidence_sha256,
        stamp_receipt_sha256=attestation_digest(signed_receipt),
        stamp_attestation_id=receipt.id,
        stamp_code=stamp.code,
        page_number=artifact.page_number,
        x_pt=artifact.x_pt,
        y_pt=artifact.y_pt,
        design_version_id=design.id if design else None,
        design_sha256=design.design_sha256 if design else None,
    )
    if (artifact.stamp_evidence_sha256 != provenance["stamp_attestation_sha256"]
            or artifact.signed_evidence_sha256 != provenance_sha256(provenance)):
        raise ValueError("Stamp placement or evidence hash mismatch")
    path = checked_stamped_pdf(artifact, current_app.config)
    return path, provenance


@stamped_pdf_api.route("/<int:artifact_id>/verify", methods=["GET"])
@jwt_required()
def verify_artifact(artifact_id):
    args = _owned(artifact_id)
    try:
        path, provenance = _verify_lineage(*args)
    except (ValueError, OSError, IngestionError, PdfFinalizationError):
        result = jsonify({"valid": False, "assurance": "platform_sealed_stamped_derivative"})
        result.headers["Cache-Control"] = "private, no-store"
        return result, 409
    artifact = args[0]
    response = jsonify({
        "valid": True, "artifact_id": artifact.id,
        "stamped_pdf_sha256": artifact.output_sha256,
        "source_signed_pdf_sha256": artifact.source_finalized_sha256,
        "stamp_provenance_sha256": artifact.signed_evidence_sha256,
        "certificate_sha256": artifact.certificate_sha256,
        "provenance": provenance,
        "assurance": "platform_sealed_stamped_derivative_not_personal_signature",
    })
    response.headers["Cache-Control"] = "private, no-store"
    return response


@stamped_pdf_api.route("/<int:artifact_id>/download", methods=["GET"])
@jwt_required()
def download_artifact(artifact_id):
    args = _owned(artifact_id)
    try:
        path, _ = _verify_lineage(*args)
    except (ValueError, OSError, IngestionError, PdfFinalizationError):
        abort(409, description="Stamped PDF lineage or signature validation failed")
    response = send_file(
        path, mimetype="application/pdf", as_attachment=True,
        download_name="TrustSeal-stamped-%s.pdf" % artifact_id,
        conditional=False, etag=False, max_age=0,
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
