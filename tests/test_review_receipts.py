"""Cryptographic review-attestation tests; no live Flask/PostgreSQL needed."""
from types import SimpleNamespace

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app.services.signing_receipts import (
    SCHEMA, canonical_bytes, public_key_id, review_payload,
    sign_receipt, verify_receipt,
)


def sample_review():
    envelope = SimpleNamespace(
        id=10, organization_id=8, document_id=20, document_blob_id=30,
        document_sha256="a" * 64,
    )
    participant = SimpleNamespace(id=40, user_id=60)
    from datetime import datetime
    decision = SimpleNamespace(
        id=50, envelope_id=10, participant_id=40, user_id=60,
        decision="acknowledged", document_sha256="a" * 64,
        consent_version="review-intent-v1", consent_sha256="b" * 64,
        recorded_at=datetime(2026, 11, 13, 10, 0, 0),
    )
    return review_payload(envelope, participant, decision)


def test_ed25519_review_receipt_verifies_with_pinned_key():
    key = Ed25519PrivateKey.generate()
    receipt = sign_receipt(sample_review(), key)
    assert receipt["key_id"] == public_key_id(key.public_key())
    assert verify_receipt(receipt, key.public_key())


def test_modified_attestation_is_rejected():
    key = Ed25519PrivateKey.generate()
    receipt = sign_receipt(sample_review(), key)
    receipt["payload"]["document_sha256"] = "f" * 64
    assert not verify_receipt(receipt, key.public_key())


def test_wrong_trust_key_and_bad_signature_are_rejected():
    key = Ed25519PrivateKey.generate()
    receipt = sign_receipt(sample_review(), key)
    assert not verify_receipt(receipt, Ed25519PrivateKey.generate().public_key())
    receipt["signature"] = "not-base64!"
    assert not verify_receipt(receipt, key.public_key())


def test_algorithm_and_schema_changes_are_rejected():
    key = Ed25519PrivateKey.generate()
    receipt = sign_receipt(sample_review(), key)
    receipt["algorithm"] = "RSA-PSS"
    assert not verify_receipt(receipt, key.public_key())
    receipt = sign_receipt(sample_review(), key)
    receipt["payload"]["schema"] = "unknown"
    assert not verify_receipt(receipt, key.public_key())


def test_canonicalization_ignores_json_key_insertion_order():
    one = {"schema": SCHEMA, "value": 1}
    two = {"value": 1, "schema": SCHEMA}
    assert canonical_bytes(one) == canonical_bytes(two)
