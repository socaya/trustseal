"""Authenticated signer-held key registration and detached PDF endorsements.

No private keys reach the server. Signatures are over canonical, nonce-bound
document digest assertions, not embedded PDF/CMS signatures or identity certificates.
"""
import hashlib
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, abort, jsonify, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.signer_cryptographic import (
    SignerPublicKey, SignerKeyChallenge, SignerEndorsementChallenge,
    SignerEndorsement,
)
from app.models.signing_envelope import SigningEnvelope, EnvelopeParticipant
from app.models.signer_decision import SignerDecision
from app.services.token_security import active_token_user
from app.services.event_delivery import enqueue
from app.services.signer_crypto import (
    parse_signer_public_key, verify_detached, enrollment_payload,
    endorsement_payload,
)
from app.blueprints.documents.api.signer_intent_api import _document_file, _decision_digest

signer_crypto_api = Blueprint("signer_crypto_api", __name__, url_prefix="/api/signer-crypto")
LIFETIME = timedelta(minutes=10)
MAX_CHALLENGES = 3


def _user():
    actor = active_token_user()
    if actor is None or not actor.is_active or actor.organization_id is None:
        abort(401)
    return actor


def _data(fields):
    obj = request.get_json(silent=True)
    if not isinstance(obj, dict) or set(obj) != fields:
        abort(400, description="Unexpected request fields")
    return obj


def _nonce():
    return secrets.token_urlsafe(32)


def _eligible(envelope_id, actor, *, lock=False):
    query = SigningEnvelope.query.filter_by(
        id=envelope_id, organization_id=actor.organization_id
    )
    envelope = (query.with_for_update() if lock else query).first()
    if envelope is None:
        abort(404)
    if envelope.state != "prepared":
        abort(409, description="Envelope is not prepared")
    participant = EnvelopeParticipant.query.filter_by(
        envelope_id=envelope.id, user_id=actor.id
    ).first()
    if participant is None:
        abort(404)
    decision = SignerDecision.query.filter_by(participant_id=participant.id).first()
    if decision is None or decision.decision != "acknowledged":
        abort(409, description="Accepted document review required")
    try:
        digest = _decision_digest(
            envelope, participant, actor.id, decision.decision,
            consent_version=decision.consent_version,
        )
    except (KeyError, ValueError):
        abort(409, description="Unsupported review consent")
    if digest != decision.consent_sha256:
        abort(409, description="Review consent integrity failure")
    if SignerEndorsement.query.filter_by(participant_id=participant.id).first():
        abort(409, description="Document has already been endorsed")
    previous = EnvelopeParticipant.query.filter(
        EnvelopeParticipant.envelope_id == envelope.id,
        EnvelopeParticipant.signing_order < participant.signing_order,
    ).all()
    for earlier in previous:
        if not SignerEndorsement.query.filter_by(participant_id=earlier.id).first():
            abort(409, description="Previous cryptographic endorsement required")
    return envelope, participant, decision


def _credential(key_id, actor):
    key = SignerPublicKey.query.filter_by(
        id=key_id, user_id=actor.id, organization_id=actor.organization_id
    ).first()
    if key is None or key.revoked_at is not None:
        abort(404, description="Active signer key not found")
    return key


@signer_crypto_api.route("/keys", methods=["GET"])
@jwt_required()
def list_signer_keys():
    actor = _user()
    items = SignerPublicKey.query.filter_by(
        user_id=actor.id, organization_id=actor.organization_id
    ).order_by(SignerPublicKey.id.desc()).limit(100).all()
    return jsonify([{
        "id": key.id, "fingerprint": key.fingerprint,
        "active": key.revoked_at is None,
        "activated_at": key.activated_at.isoformat(),
    } for key in items])


@signer_crypto_api.route("/keys/challenge", methods=["POST"])
@jwt_required()
def issue_key_challenge():
    actor = _user()
    data = _data({"public_key_pem"})
    try:
        _, normalized, fingerprint = parse_signer_public_key(data["public_key_pem"])
    except ValueError:
        abort(400, description="Valid Ed25519 public key required")
    if SignerPublicKey.query.filter_by(fingerprint=fingerprint).first():
        abort(409, description="Key already registered")
    now = datetime.utcnow()
    recent = SignerKeyChallenge.query.filter(
        SignerKeyChallenge.user_id == actor.id,
        SignerKeyChallenge.issued_at >= now - LIFETIME,
    ).count()
    if recent >= MAX_CHALLENGES:
        abort(429, description="Enrollment attempt limit")
    nonce = _nonce()
    record = SignerKeyChallenge(
        user_id=actor.id, organization_id=actor.organization_id,
        fingerprint=fingerprint, public_key_pem=normalized,
        nonce_hash=hashlib.sha256(nonce.encode("ascii")).hexdigest(),
        issued_at=now, expires_at=now + LIFETIME,
    )
    db.session.add(record)
    db.session.commit()
    result = jsonify({
        "challenge_id": record.id,
        "sign_this": enrollment_payload(
            user_id=actor.id, organization_id=actor.organization_id,
            fingerprint=fingerprint, nonce=nonce,
        ),
        "expires_at": record.expires_at.isoformat(),
        "algorithm": "Ed25519",
    })
    result.headers["Cache-Control"] = "no-store"
    return result, 201


@signer_crypto_api.route("/keys/confirm", methods=["POST"])
@jwt_required()
def confirm_key():
    actor = _user()
    data = _data({"challenge_id", "nonce", "signature_b64"})
    if type(data["challenge_id"]) is not int or not isinstance(data["nonce"], str):
        abort(400)
    challenge = SignerKeyChallenge.query.filter_by(
        id=data["challenge_id"], user_id=actor.id,
        organization_id=actor.organization_id,
    ).with_for_update().first()
    now = datetime.utcnow()
    if (challenge is None or challenge.consumed_at is not None
            or challenge.expires_at <= now
            or not secrets.compare_digest(
                hashlib.sha256(data["nonce"].encode("utf-8")).hexdigest(),
                challenge.nonce_hash,
            )):
        abort(409, description="Challenge invalid or expired")
    payload = enrollment_payload(
        user_id=actor.id, organization_id=actor.organization_id,
        fingerprint=challenge.fingerprint, nonce=data["nonce"],
    )
    if not verify_detached(challenge.public_key_pem, payload, data["signature_b64"]):
        abort(403, description="Private-key proof failed")
    if SignerPublicKey.query.filter_by(fingerprint=challenge.fingerprint).first():
        abort(409, description="Key already registered")
    challenge.consumed_at = now
    key = SignerPublicKey(
        user_id=actor.id, organization_id=actor.organization_id,
        fingerprint=challenge.fingerprint,
        public_key_pem=challenge.public_key_pem,
        activated_at=now,
    )
    db.session.add(key)
    db.session.flush()
    enqueue(
        event_type="signer.key.registered", aggregate_type="signer_key",
        aggregate_id=key.id, organization_id=actor.organization_id,
        actor_id=actor.id, action="signer.key.registered",
        idempotency_key="signer-key-registered:%s" % key.id,
    )
    db.session.commit()
    return jsonify({"id": key.id, "fingerprint": key.fingerprint,
                    "assurance": "private_key_possession_only"}), 201


@signer_crypto_api.route("/keys/<int:key_id>/revoke", methods=["POST"])
@jwt_required()
def revoke_key(key_id):
    actor = _user()
    key = SignerPublicKey.query.filter_by(
        id=key_id, user_id=actor.id,
        organization_id=actor.organization_id
    ).with_for_update().first()
    if key is None:
        abort(404)
    if key.revoked_at is None:
        key.revoked_at = datetime.utcnow()
        enqueue(
            event_type="signer.key.revoked", aggregate_type="signer_key",
            aggregate_id=key.id, organization_id=actor.organization_id,
            actor_id=actor.id, action="signer.key.revoked",
            idempotency_key="signer-key-revoked:%s" % key.id,
        )
        db.session.commit()
    return jsonify({"id": key.id, "active": False})


@signer_crypto_api.route("/envelopes/<int:envelope_id>/challenge", methods=["POST"])
@jwt_required()
def issue_endorsement_challenge(envelope_id):
    actor = _user()
    data = _data({"key_id"})
    if type(data["key_id"]) is not int:
        abort(400)
    envelope, participant, decision = _eligible(envelope_id, actor, lock=True)
    key = _credential(data["key_id"], actor)
    _document_file(envelope)
    now = datetime.utcnow()
    recent = SignerEndorsementChallenge.query.filter(
        SignerEndorsementChallenge.participant_id == participant.id,
        SignerEndorsementChallenge.issued_at >= now - LIFETIME,
    ).count()
    if recent >= MAX_CHALLENGES:
        abort(429, description="Endorsement attempt limit")
    nonce = _nonce()
    payload = endorsement_payload(
        envelope=envelope, participant=participant, decision=decision,
        fingerprint=key.fingerprint, nonce=nonce,
    )
    challenge = SignerEndorsementChallenge(
        envelope_id=envelope.id, participant_id=participant.id,
        user_id=actor.id, signer_key_id=key.id,
        nonce_hash=hashlib.sha256(nonce.encode("ascii")).hexdigest(),
        signed_payload=payload, issued_at=now, expires_at=now + LIFETIME,
    )
    db.session.add(challenge)
    db.session.commit()
    result = jsonify({
        "challenge_id": challenge.id, "sign_this": payload,
        "expires_at": challenge.expires_at.isoformat(),
        "algorithm": "Ed25519",
    })
    result.headers["Cache-Control"] = "no-store"
    return result, 201


@signer_crypto_api.route("/envelopes/<int:envelope_id>/endorse", methods=["POST"])
@jwt_required()
def record_endorsement(envelope_id):
    actor = _user()
    data = _data({"challenge_id", "signature_b64"})
    if type(data["challenge_id"]) is not int:
        abort(400)
    envelope, participant, decision = _eligible(envelope_id, actor, lock=True)
    challenge = SignerEndorsementChallenge.query.filter_by(
        id=data["challenge_id"], envelope_id=envelope.id,
        participant_id=participant.id, user_id=actor.id,
    ).with_for_update().first()
    now = datetime.utcnow()
    if (challenge is None or challenge.consumed_at is not None
            or challenge.expires_at <= now):
        abort(409, description="Challenge unavailable")
    key = _credential(challenge.signer_key_id, actor)
    payload = challenge.signed_payload
    if (payload.get("key_fingerprint") != key.fingerprint
            or payload.get("nonce") is None
            or hashlib.sha256(payload["nonce"].encode("utf-8")).hexdigest() != challenge.nonce_hash):
        abort(409, description="Signing challenge corrupted")
    expected = endorsement_payload(
        envelope=envelope, participant=participant, decision=decision,
        fingerprint=key.fingerprint, nonce=payload["nonce"],
    )
    if expected != payload:
        abort(409, description="Document or consent binding changed")
    if not verify_detached(key.public_key_pem, payload, data["signature_b64"]):
        abort(403, description="Signer signature invalid")
    _document_file(envelope)
    challenge.consumed_at = now
    record = SignerEndorsement(
        envelope_id=envelope.id, participant_id=participant.id,
        user_id=actor.id, signer_key_id=key.id,
        challenge_id=challenge.id, signed_payload=payload,
        signature_b64=data["signature_b64"], signed_at=now,
    )
    db.session.add(record)
    db.session.flush()
    enqueue(
        event_type="signer.document.endorsed", aggregate_type="envelope",
        aggregate_id=envelope.id, organization_id=envelope.organization_id,
        actor_id=actor.id, action="signer.document.endorsed",
        idempotency_key="signer-document-endorsed:%s" % participant.id,
    )
    db.session.commit()
    return jsonify({
        "id": record.id, "envelope_id": envelope.id,
        "participant_id": participant.id, "key_fingerprint": key.fingerprint,
        "signed_payload": payload, "signature_b64": record.signature_b64,
        "assurance": "signer_held_key_detached_endorsement_not_pades",
    }), 201


@signer_crypto_api.route("/envelopes/<int:envelope_id>/endorsement", methods=["GET"])
@jwt_required()
def read_endorsement(envelope_id):
    actor = _user()
    envelope = SigningEnvelope.query.filter_by(
        id=envelope_id, organization_id=actor.organization_id
    ).first()
    if envelope is None:
        abort(404)
    assigned = EnvelopeParticipant.query.filter_by(
        envelope_id=envelope.id, user_id=actor.id
    ).first()
    if envelope.created_by_id != actor.id and assigned is None:
        abort(404)
    items = SignerEndorsement.query.filter_by(envelope_id=envelope.id).order_by(
        SignerEndorsement.id
    ).all()
    results = []
    for item in items:
        key = db.session.get(SignerPublicKey, item.signer_key_id)
        results.append({
            "participant_id": item.participant_id, "user_id": item.user_id,
            "signed_payload": item.signed_payload,
            "signature_b64": item.signature_b64,
            "public_key_pem": key.public_key_pem if key else None,
            "signature_valid": bool(key and verify_detached(
                key.public_key_pem, item.signed_payload, item.signature_b64
            )),
            "key_revoked": bool(key is None or key.revoked_at is not None),
            "assurance": "signer_held_key_detached_endorsement_not_pades",
        })
    response = jsonify(results)
    response.headers["Cache-Control"] = "no-store"
    return response
