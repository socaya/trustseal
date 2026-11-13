"""Authorized retrieval and validation of one platform-sealed PDF per envelope.

This is a platform certificate seal, not the participant's digital signature.
A valid trust chain does not establish identity-proofing or legal sufficiency.
"""
from flask import Blueprint, abort, current_app, jsonify, send_file
from flask_jwt_extended import jwt_required
from app.extensions import db
from app.models.pdf_finalization import FinalizedPdf
from app.models.signing_envelope import SigningEnvelope, EnvelopeParticipant
from app.services.token_security import active_token_user
from app.services.documents.private_storage import check_object_digest, IngestionError
from app.services.platform_pdf_seal import inspect_signed_pdf, PdfFinalizationError

sealed_pdf_api = Blueprint("sealed_pdf_api", __name__, url_prefix="/api/platform-sealed-pdfs")


def _authorized(envelope_id):
    actor = active_token_user()
    if actor is None or not actor.is_active or actor.organization_id is None:
        abort(401)
    envelope = SigningEnvelope.query.filter_by(
        id=envelope_id, organization_id=actor.organization_id
    ).first()
    if envelope is None:
        abort(404)
    participant = EnvelopeParticipant.query.filter_by(
        envelope_id=envelope.id, user_id=actor.id
    ).first()
    if envelope.created_by_id != actor.id and participant is None:
        abort(404)
    record = FinalizedPdf.query.filter_by(
        envelope_id=envelope.id, organization_id=envelope.organization_id
    ).first()
    if record is None:
        abort(404)
    return envelope, record


def _checked_path(record):
    try:
        return check_object_digest(
            record.object_key, record.output_sha256, current_app.config
        )
    except IngestionError:
        abort(503, description="Platform-sealed PDF storage integrity unavailable")


@sealed_pdf_api.route("/envelopes/<int:envelope_id>/verify", methods=["GET"])
@jwt_required()
def verify_platform_pdf(envelope_id):
    envelope, record = _authorized(envelope_id)
    path = _checked_path(record)
    try:
        status = inspect_signed_pdf(path.read_bytes(), current_app.config)
    except PdfFinalizationError:
        status = {
            "signature_valid": False, "intact": False,
            "trusted": False, "overall_valid": False,
        }
    status.update({
        "artifact_id": record.id,
        "envelope_id": envelope.id,
        "source_sha256": record.source_sha256,
        "output_sha256": record.output_sha256,
        "assurance": "platform_certificate_seal_not_individual_signatures",
        "not_individual_signatures": True,
    })
    response = jsonify(status)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@sealed_pdf_api.route("/envelopes/<int:envelope_id>/download", methods=["GET"])
@jwt_required()
def download_platform_pdf(envelope_id):
    envelope, record = _authorized(envelope_id)
    path = _checked_path(record)
    try:
        result = inspect_signed_pdf(path.read_bytes(), current_app.config)
    except PdfFinalizationError:
        abort(503, description="PDF certificate validation unavailable")
    if not result["overall_valid"]:
        abort(409, description="Platform PDF seal did not validate")
    response = send_file(
        path, mimetype="application/pdf", as_attachment=True,
        download_name="TrustSeal-platform-sealed-%s.pdf" % envelope.id,
        conditional=False, etag=False, max_age=0,
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
