"""Tenant-scoped verification of stored platform review attestations.

The verifier uses a pinned public key and never accepts a public key supplied
by the client. A valid receipt attests to a review *record*, not a signed PDF.
"""
from flask import Blueprint, abort, current_app, jsonify
from flask_jwt_extended import jwt_required
from app.extensions import db
from app.models.review_receipt import ReviewReceipt
from app.models.signing_envelope import SigningEnvelope, EnvelopeParticipant
from app.models.signer_decision import SignerDecision
from app.services.token_security import active_token_user
from app.services.signing_receipts import resolve_trusted_public_key, verify_receipt, review_payload

receipt_api = Blueprint("receipt_api", __name__, url_prefix="/api/review-receipts")


@receipt_api.route("/<int:receipt_id>", methods=["GET"])
@jwt_required()
def verify_stored_receipt(receipt_id):
    user = active_token_user()
    if user is None or not user.is_active or user.organization_id is None:
        abort(401)
    record = db.session.get(ReviewReceipt, receipt_id)
    if record is None or record.organization_id != user.organization_id:
        abort(404)
    envelope = db.session.get(SigningEnvelope, record.envelope_id)
    if envelope is None or envelope.organization_id != user.organization_id:
        abort(404)
    participant = EnvelopeParticipant.query.filter_by(
        envelope_id=envelope.id, user_id=user.id
    ).first()
    if envelope.created_by_id != user.id and participant is None:
        abort(404)
    decision = db.session.get(SignerDecision, record.decision_id)
    if decision is None or decision.envelope_id != envelope.id:
        abort(409, description="Receipt references inconsistent evidence")
    receipt = {
        "payload": record.payload,
        "algorithm": record.algorithm,
        "key_id": record.key_id,
        "signature": record.signature,
    }
    try:
        trusted_key = resolve_trusted_public_key(current_app.config, record.key_id)
    except (OSError, ValueError, TypeError):
        abort(503, description="Trusted receipt verifier is unavailable")
    verified = verify_receipt(receipt, trusted_key)
    signer = db.session.get(EnvelopeParticipant, decision.participant_id)
    try:
        expected = review_payload(envelope, signer, decision)
        bound = (
            record.organization_id == envelope.organization_id
            and record.decision_id == decision.id
            and record.envelope_id == decision.envelope_id
            and record.payload == expected
        )
    except (AttributeError, ValueError, TypeError):
        bound = False
    response = jsonify({
        "id": record.id,
        "valid": bool(verified and bound),
        "crypto_valid": bool(verified),
        "record_binding_valid": bool(bound),
        "key_id": record.key_id,
        "assurance": "platform_attestation_of_review_only",
        "not_a_pdf_signature": True,
    })
    response.headers["Cache-Control"] = "no-store"
    return response


@receipt_api.route("/<int:receipt_id>/export", methods=["GET"])
@jwt_required()
def export_detached_receipt(receipt_id):
    """Export the detached signed statement, never the signing private key."""
    user = active_token_user()
    if user is None or not user.is_active or user.organization_id is None:
        abort(401)
    record = db.session.get(ReviewReceipt, receipt_id)
    if record is None or record.organization_id != user.organization_id:
        abort(404)
    envelope = db.session.get(SigningEnvelope, record.envelope_id)
    if envelope is None or envelope.organization_id != user.organization_id:
        abort(404)
    participant = EnvelopeParticipant.query.filter_by(
        envelope_id=envelope.id, user_id=user.id
    ).first()
    if envelope.created_by_id != user.id and participant is None:
        abort(404)
    response = jsonify({
        "payload": record.payload,
        "algorithm": record.algorithm,
        "key_id": record.key_id,
        "signature": record.signature,
        "assurance": "platform_attestation_of_review_only",
        "not_a_pdf_signature": True,
    })
    response.headers["Cache-Control"] = "private, no-store"
    return response
