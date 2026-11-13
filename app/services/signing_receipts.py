"""Detached Ed25519 receipts for recorded signer decisions.

A receipt authenticates TrustSeal's own assertion about a review event; it is
NOT the human signer's signature and does NOT sign PDF bytes in PDF/PAdES.
Private keys must be protected outside the application repository.
"""
import base64
import hashlib
import json
import stat
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


SCHEMA = "trustseal.review-receipt.v1"


def canonical_bytes(payload):
    if not isinstance(payload, dict):
        raise ValueError("Receipt payload must be a dictionary")
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def public_key_id(public_key):
    data = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return "ed25519-sha256:" + hashlib.sha256(data).hexdigest()


def load_private_key(path):
    if not path or not Path(path).is_absolute():
        raise ValueError("Absolute protected signing key path is required")
    key_path = Path(path)
    if key_path.is_symlink() or not key_path.is_file():
        raise ValueError("Protected private signing key file required")
    if stat.S_IMODE(key_path.stat().st_mode) & 0o077:
        raise ValueError("Private signing key must not be group/world accessible")
    pem = key_path.read_bytes()
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Expected an Ed25519 private key")
    return key


def load_public_key(path):
    if not path or not Path(path).is_absolute():
        raise ValueError("Absolute trusted public key path is required")
    key = serialization.load_pem_public_key(Path(path).read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("Expected Ed25519 public key")
    return key


def sign_receipt(payload, private_key):
    if payload.get("schema") != SCHEMA:
        raise ValueError("Unsupported receipt schema")
    signature = private_key.sign(canonical_bytes(payload))
    return {
        "payload": payload,
        "algorithm": "Ed25519",
        "key_id": public_key_id(private_key.public_key()),
        "signature": base64.b64encode(signature).decode("ascii"),
    }


def verify_receipt(receipt, trusted_public_key):
    """Check algorithm, pinned key, signature and canonical contents."""
    try:
        if receipt["algorithm"] != "Ed25519":
            return False
        if receipt["key_id"] != public_key_id(trusted_public_key):
            return False
        if receipt["payload"].get("schema") != SCHEMA:
            return False
        sig = base64.b64decode(receipt["signature"], validate=True)
        trusted_public_key.verify(sig, canonical_bytes(receipt["payload"]))
        return True
    except (KeyError, TypeError, ValueError, InvalidSignature):
        return False


def review_payload(envelope, participant, decision):
    if decision.decision not in ("acknowledged", "declined"):
        raise ValueError("Unrecognized review decision")
    if (decision.envelope_id != envelope.id or
            decision.participant_id != participant.id or
            decision.user_id != participant.user_id or
            decision.document_sha256 != envelope.document_sha256):
        raise ValueError("Inconsistent review evidence")
    if not decision.recorded_at:
        raise ValueError("Review timestamp required")
    return {
        "schema": SCHEMA,
        "assurance": "platform_attestation_of_review_only",
        "envelope_id": envelope.id,
        "organization_id": envelope.organization_id,
        "document_id": envelope.document_id,
        "document_blob_id": envelope.document_blob_id,
        "document_sha256": envelope.document_sha256,
        "participant_id": participant.id,
        "review_decision_id": decision.id,
        "decision": decision.decision,
        "consent_version": decision.consent_version,
        "consent_sha256": decision.consent_sha256,
        "recorded_at": decision.recorded_at.isoformat(timespec="microseconds") + "Z",
    }
