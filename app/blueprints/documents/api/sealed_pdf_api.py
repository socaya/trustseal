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
    if record.source_blob_id != envelope.document_blob_id or record.source_sha256 != envelope.document_sha256:
        abort(409, description="Finalized PDF source mismatch")
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
        status = inspect_signed_pdf(
            path.read_bytes(), current_app.config,
            expected_evidence_sha256=record.evidence_sha256,
        )
    except PdfFinalizationError:
        status = {
            "signature_valid": False, "intact": False,
            "trusted": False, "overall_valid": False,
        }
    status.update({
        "artifact_id": record.id,
        "issued_by_id": record.issued_by_id,
        "envelope_id": envelope.id,
        "source_sha256": record.source_sha256,
        "evidence_sha256": record.evidence_sha256,
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
        result = inspect_signed_pdf(
            path.read_bytes(), current_app.config,
            expected_evidence_sha256=record.evidence_sha256,
        )
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


@sealed_pdf_api.route("/envelopes/<int:envelope_id>/evidence", methods=["GET"])
@jwt_required()
def export_platform_seal_evidence(envelope_id):
    """Export and verify the exact review receipts bound into the PDF seal."""
    from app.models.signer_decision import SignerDecision
    from app.models.review_receipt import ReviewReceipt
    from app.services.signing_receipts import (
        resolve_trusted_public_key, verify_receipt, review_payload,
    )
    from app.services.platform_review_evidence import (
        canonical_evidence_bundle, evidence_digest,
    )
    envelope, record = _authorized(envelope_id)
    participants = EnvelopeParticipant.query.filter_by(
        envelope_id=envelope.id
    ).order_by(EnvelopeParticipant.signing_order).all()
    items = []
    for participant in participants:
        decision = SignerDecision.query.filter_by(participant_id=participant.id).first()
        if decision is None or decision.decision != "acknowledged":
            abort(409, description="Review record incomplete")
        receipt = ReviewReceipt.query.filter_by(decision_id=decision.id).first()
        if receipt is None:
            abort(409, description="Signed evidence is missing")
        detached = {
            "payload": receipt.payload,
            "algorithm": receipt.algorithm,
            "key_id": receipt.key_id,
            "signature": receipt.signature,
        }
        try:
            trusted = resolve_trusted_public_key(current_app.config, receipt.key_id)
            valid = verify_receipt(detached, trusted)
            expected = review_payload(envelope, participant, decision)
        except (ValueError, OSError, TypeError, KeyError):
            abort(503, description="Receipt trust configuration unavailable")
        if not valid or expected != receipt.payload:
            abort(409, description="Signed review evidence failed verification")
        items.append({
            "participant_id": participant.id,
            "signing_order": participant.signing_order,
            "review_decision_id": decision.id,
            **detached,
        })
    try:
        bundle = canonical_evidence_bundle(envelope.id, items)
        computed = evidence_digest(bundle)
    except ValueError:
        abort(409, description="Evidence sequence is invalid")
    if computed != record.evidence_sha256:
        abort(409, description="Evidence hash does not match sealed PDF")
    response = jsonify({
        "bundle": bundle,
        "evidence_sha256": computed,
        "source_sha256": record.source_sha256,
        "output_sha256": record.output_sha256,
        "assurance": "platform_certificate_seal_not_individual_signatures",
    })
    response.headers["Cache-Control"] = "private, no-store"
    return response
