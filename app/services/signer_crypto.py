"""Signer-controlled detached Ed25519 endorsements.

TrustSeal never receives a signer private key. Proof of key possession does
not establish independently verified identity or create a PAdES PDF signature.
"""
import base64
import hashlib
import json
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

KEY_ENROLL_SCHEMA = "trustseal.signer-key-enrollment.v1"
ENDORSE_SCHEMA = "trustseal.signer-document-endorsement.v1"


def canonical_message(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def parse_signer_public_key(pem):
    if not isinstance(pem, str) or not 1 <= len(pem) <= 2048:
        raise ValueError("PEM public key required")
    try:
        key = serialization.load_pem_public_key(pem.encode("ascii"))
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("Invalid signer public key") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("Only Ed25519 signer public keys are accepted")
    normalized = key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("ascii")
    fingerprint = hashlib.sha256(key.public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )).hexdigest()
    return key, normalized, fingerprint


def verify_detached(pem, payload, signature_b64):
    if not isinstance(signature_b64, str) or len(signature_b64) > 256:
        return False
    try:
        key, _, _ = parse_signer_public_key(pem)
        signature = base64.b64decode(signature_b64, validate=True)
        if len(signature) != 64:
            return False
        key.verify(signature, canonical_message(payload))
        return True
    except (InvalidSignature, TypeError, ValueError):
        return False


def enrollment_payload(*, user_id, organization_id, fingerprint, nonce):
    if not isinstance(nonce, str) or not 20 <= len(nonce) <= 128:
        raise ValueError("Invalid enrollment challenge")
    return {
        "schema": KEY_ENROLL_SCHEMA, "user_id": user_id,
        "organization_id": organization_id,
        "key_fingerprint": fingerprint, "nonce": nonce,
        "purpose": "register_signer_controlled_key",
    }


def endorsement_payload(*, envelope, participant, decision, fingerprint, nonce):
    if not isinstance(nonce, str) or not 20 <= len(nonce) <= 128:
        raise ValueError("Invalid endorsement challenge")
    if (decision.decision != "acknowledged"
            or decision.participant_id != participant.id
            or decision.envelope_id != envelope.id
            or decision.user_id != participant.user_id
            or decision.document_sha256 != envelope.document_sha256):
        raise ValueError("Review evidence does not match signing context")
    if not re.fullmatch(r"[0-9a-f]{64}", envelope.document_sha256):
        raise ValueError("Invalid document digest")
    return {
        "schema": ENDORSE_SCHEMA, "envelope_id": envelope.id,
        "organization_id": envelope.organization_id,
        "participant_id": participant.id, "user_id": participant.user_id,
        "signing_order": participant.signing_order,
        "document_id": envelope.document_id,
        "document_blob_id": envelope.document_blob_id,
        "document_sha256": envelope.document_sha256,
        "review_decision_id": decision.id,
        "review_consent_sha256": decision.consent_sha256,
        "key_fingerprint": fingerprint, "nonce": nonce,
        "purpose": "signer_controlled_detached_document_endorsement",
    }
