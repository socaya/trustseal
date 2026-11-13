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
from app.services.signing_receipts import load_public_key, verify_receipt

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
        trusted_key = load_public_key(
            current_app.config.get("REVIEW_RECEIPT_PUBLIC_KEY")
        )
    except (OSError, ValueError, TypeError):
        abort(503, description="Trusted receipt verifier is unavailable")
    verified = verify_receipt(receipt, trusted_key)
    payload = record.payload
    # A valid detached signature must also correspond to the current
    # immutable decision and exact prepared PDF reference.
    bound = (
        payload.get("envelope_id") == envelope.id
        and payload.get("review_decision_id") == decision.id
        and payload.get("document_sha256") == envelope.document_sha256
        and payload.get("decision") == decision.decision
        and payload.get("consent_sha256") == decision.consent_sha256
        and payload.get("participant_id") == decision.participant_id
        and payload.get("organization_id") == envelope.organization_id
    )
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
