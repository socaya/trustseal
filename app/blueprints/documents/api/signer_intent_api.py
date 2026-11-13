"""Signer intent acknowledgements, separate from cryptographic signing.

A recent password check issues a one-time nonce bound to one prepared PDF
digest and participant. Only the authenticated participant can consume it.
An acknowledgement is NOT a completed electronic signature.
"""
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, abort, current_app, jsonify, request, send_file
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.user import User
from app.models.documents.document_blob import DocumentBlob
from app.models.signing_envelope import SigningEnvelope, EnvelopeParticipant
from app.models.signer_decision import SignerChallenge, SignerDecision
from app.services.token_security import active_token_user
from app.services.event_delivery import enqueue
from app.services.documents.private_storage import IngestionError, check_object_digest

signer_intent_api = Blueprint(
    "signer_intent_api", __name__, url_prefix="/api/signer-intent"
)

CONSENT_VERSION = "review-intent-v1"
CONSENT_TEXT = (
    "I acknowledge that I have reviewed the identified document revision. "
    "This records my review decision only; it is not a cryptographic "
    "signature or a completed legally signed PDF."
)
# Existing wording must never be rewritten after decisions are recorded.
CONSENT_REGISTRY = {CONSENT_VERSION: CONSENT_TEXT}
CHALLENGE_SECONDS = 600
MAX_CHALLENGES_PER_10_MIN = 3


def _actor():
    user = active_token_user()
    if user is None or not user.is_active or user.organization_id is None:
        abort(401)
    return user


def _payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="JSON object required")
    return data


def _participant(envelope_id, user, lock=False):
    """Lock the envelope before checking consent and signing order."""
    query = SigningEnvelope.query.filter_by(
        id=envelope_id, organization_id=user.organization_id
    )
    envelope = (query.with_for_update() if lock else query).first()
    if envelope is None:
        abort(404)
    participant = EnvelopeParticipant.query.filter_by(
        envelope_id=envelope.id, user_id=user.id
    ).first()
    if participant is None:
        abort(404)
    return envelope, participant


def _eligible(envelope, participant):
    if envelope.state != "prepared":
        abort(409, description="Envelope is not prepared or was cancelled")
    earlier = EnvelopeParticipant.query.filter(
        EnvelopeParticipant.envelope_id == envelope.id,
        EnvelopeParticipant.signing_order < participant.signing_order,
    ).all()
    decisions = SignerDecision.query.filter_by(envelope_id=envelope.id).all()
    decided = {d.participant_id: d.decision for d in decisions}
    if participant.id in decided:
        abort(409, description="A decision has already been recorded")
    if any(d.decision == "declined" for d in decisions):
        abort(409, description="Envelope has a declined participant")
    if any(decided.get(p.id) != "acknowledged" for p in earlier):
        abort(409, description="Earlier signing-order participants have not acknowledged")


def _document_file(envelope):
    blob = db.session.get(DocumentBlob, envelope.document_blob_id)
    if (blob is None or blob.document_id != envelope.document_id
            or not hmac.compare_digest(blob.sha256, envelope.document_sha256)):
        abort(409, description="Envelope document manifest mismatch")
    try:
        return blob, check_object_digest(blob.object_key, blob.sha256, current_app.config)
    except IngestionError:
        abort(503, description="Document file is unavailable or fails integrity validation")


def _decision_digest(envelope, participant, user_id, decision, consent_version=CONSENT_VERSION):
    consent_text = CONSENT_REGISTRY[consent_version]
    payload = {
        "schema": 1, "consent_version": consent_version,
        "consent_text": consent_text, "envelope_id": envelope.id,
        "participant_id": participant.id, "user_id": user_id,
        "document_sha256": envelope.document_sha256, "decision": decision,
    }
    canonical = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _decision_data(item):
    return {
        "id": item.id, "envelope_id": item.envelope_id,
        "participant_id": item.participant_id, "user_id": item.user_id,
        "decision": item.decision, "document_sha256": item.document_sha256,
        "consent_version": item.consent_version,
        "consent_sha256": item.consent_sha256,
        "recorded_at": item.recorded_at.isoformat() if item.recorded_at else None,
        "assurance": "authenticated_review_intent_not_signature",
    }


@signer_intent_api.route("/envelopes/<int:envelope_id>", methods=["GET"])
@jwt_required()
def signer_envelope(envelope_id):
    user = _actor()
    envelope, participant = _participant(envelope_id, user)
    decision = SignerDecision.query.filter_by(participant_id=participant.id).first()
    response = jsonify({
        "envelope_id": envelope.id, "state": envelope.state,
        "document_sha256": envelope.document_sha256,
        "document_blob_id": envelope.document_blob_id,
        "signing_order": participant.signing_order,
        "consent_version": CONSENT_VERSION,
        "consent_text": CONSENT_TEXT,
        "decision": _decision_data(decision) if decision else None,
        "assurance": "review_intent_only",
    })
    response.headers["Cache-Control"] = "no-store"
    return response


@signer_intent_api.route("/envelopes/<int:envelope_id>/document", methods=["GET"])
@jwt_required()
def signer_document(envelope_id):
    user = _actor()
    envelope, participant = _participant(envelope_id, user)
    if envelope.state != "prepared":
        abort(409, description="Envelope is not prepared")
    blob, path = _document_file(envelope)
    response = send_file(
        path, mimetype="application/pdf", as_attachment=True,
        download_name=blob.file_name, conditional=False, etag=False, max_age=0,
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@signer_intent_api.route("/envelopes/<int:envelope_id>/challenge", methods=["POST"])
@jwt_required()
def issue_challenge(envelope_id):
    user = _actor()
    data = _payload()
    if (set(data) != {"password"} or not isinstance(data["password"], str)
            or not 1 <= len(data["password"]) <= 1024):
        abort(400, description="Password reauthentication required")
    envelope, participant = _participant(envelope_id, user, lock=True)
    _eligible(envelope, participant)
    # Throttle attempts BEFORE password evaluation, preventing unlimited
    # challenge endpoint guessing. Invalid passwords are not logged or stored.
    now = datetime.utcnow()
    window = now - timedelta(minutes=10)
    count = SignerChallenge.query.filter(
        SignerChallenge.participant_id == participant.id,
        SignerChallenge.issued_at > window,
    ).count()
    if count >= MAX_CHALLENGES_PER_10_MIN:
        abort(429, description="Too many review challenges")
    if not user.check_password(data["password"]):
        # Persist a nonusable, already-consumed attempt so failures count
        # towards the same per-participant lockout as successful issuance.
        failed = SignerChallenge(
            envelope_id=envelope.id, participant_id=participant.id,
            user_id=user.id, document_sha256=envelope.document_sha256,
            nonce_sha256=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
            issued_at=now, expires_at=now + timedelta(seconds=CHALLENGE_SECONDS),
            consumed_at=now,
        )
        db.session.add(failed)
        db.session.commit()
        abort(403, description="Reauthentication failed")
    _document_file(envelope)
    nonce = secrets.token_urlsafe(32)
    record = SignerChallenge(
        envelope_id=envelope.id, participant_id=participant.id,
        user_id=user.id,
        document_sha256=envelope.document_sha256,
        nonce_sha256=hashlib.sha256(nonce.encode("utf-8")).hexdigest(),
        issued_at=now,
        expires_at=now + timedelta(seconds=CHALLENGE_SECONDS),
    )
    db.session.add(record)
    db.session.commit()
    response = jsonify({
        "challenge_id": record.id, "challenge": nonce,
        "expires_at": record.expires_at.isoformat(),
        "document_sha256": envelope.document_sha256,
        "consent_version": CONSENT_VERSION,
        "consent_text": CONSENT_TEXT,
        "assurance": "review_intent_only",
    })
    response.headers["Cache-Control"] = "no-store"
    return response, 201


@signer_intent_api.route("/envelopes/<int:envelope_id>/decision", methods=["POST"])
@jwt_required()
def record_decision(envelope_id):
    user = _actor()
    data = _payload()
    if set(data) != {"challenge_id", "challenge", "decision", "document_sha256", "consent_version", "affirmed"}:
        abort(400, description="Complete consent decision payload required")
    decision = data["decision"]
    if decision not in ("acknowledged", "declined") or type(decision) is not str:
        abort(400, description="Invalid decision")
    if (data["consent_version"] != CONSENT_VERSION
            or type(data["affirmed"]) is not bool or data["affirmed"] is not True):
        abort(400, description="Explicit acknowledgement of the displayed statement required")
    if (type(data["challenge_id"]) is not int
            or not isinstance(data["challenge"], str)
            or not 1 <= len(data["challenge"]) <= 256):
        abort(400, description="Invalid challenge")
    envelope, participant = _participant(envelope_id, user, lock=True)
    _eligible(envelope, participant)
    if (not isinstance(data["document_sha256"], str)
            or not hmac.compare_digest(data["document_sha256"], envelope.document_sha256)):
        abort(409, description="Document digest changed")
    challenge = SignerChallenge.query.filter_by(
        id=data["challenge_id"], envelope_id=envelope.id,
        participant_id=participant.id, user_id=user.id,
    ).with_for_update().first()
    now = datetime.utcnow()
    if (challenge is None or challenge.consumed_at is not None
            or challenge.expires_at <= now
            or challenge.document_sha256 != envelope.document_sha256):
        abort(409, description="Challenge unavailable or expired")
    if not hmac.compare_digest(
        hashlib.sha256(data["challenge"].encode("utf-8")).hexdigest(),
        challenge.nonce_sha256
    ):
        abort(403, description="Invalid challenge")
    _document_file(envelope)
    challenge.consumed_at = now
    record = SignerDecision(
        envelope_id=envelope.id, participant_id=participant.id,
        user_id=user.id, challenge_id=challenge.id,
        decision=decision, document_sha256=envelope.document_sha256,
        consent_version=CONSENT_VERSION,
        consent_sha256=_decision_digest(envelope, participant, user.id, decision),
        recorded_at=now,
    )
    db.session.add(record)
    db.session.flush()
    enqueue(
        event_type="envelope.review." + decision,
        aggregate_type="envelope", aggregate_id=envelope.id,
        organization_id=envelope.organization_id, actor_id=user.id,
        action="envelope.review." + decision,
        idempotency_key="envelope-review:%s" % participant.id,
    )
    db.session.commit()
    response = jsonify(_decision_data(record))
    response.headers["Cache-Control"] = "no-store"
    return response, 201
