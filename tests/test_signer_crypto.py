"""End-to-end cryptographic unit tests for signer-held key possession.

The key is created by this test and never uploaded. These tests exercise
real Ed25519 signing, nonce binding, consent binding and tampering.
PostgreSQL endpoint tests are separate release gates.
"""
import base64
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from app.services.signer_crypto import (
    parse_signer_public_key, enrollment_payload, endorsement_payload,
    verify_detached, canonical_message,
)


def _keypair():
    secret = Ed25519PrivateKey.generate()
    public = secret.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return secret, public


def _sign(private, payload):
    return base64.b64encode(private.sign(canonical_message(payload))).decode("ascii")


def _context():
    envelope = SimpleNamespace(
        id=21, organization_id=4, document_id=7,
        document_blob_id=9, document_sha256="a" * 64,
    )
    participant = SimpleNamespace(id=14, user_id=33, signing_order=1)
    decision = SimpleNamespace(
        id=80, envelope_id=21, participant_id=14,
        user_id=33, document_sha256="a" * 64,
        decision="acknowledged", consent_sha256="b" * 64,
    )
    return envelope, participant, decision


def test_key_enrollment_requires_control_of_private_key():
    private, public = _keypair()
    key, normalized, fingerprint = parse_signer_public_key(public)
    assert normalized == public
    assert len(fingerprint) == 64
    payload = enrollment_payload(
        user_id=33, organization_id=4, fingerprint=fingerprint,
        nonce="random-unique-nonce-123456789",
    )
    signature = _sign(private, payload)
    assert verify_detached(public, payload, signature)
    assert not verify_detached(public, {**payload, "user_id": 99}, signature)
    assert not verify_detached(public, {**payload, "nonce": "different-nonce-123456789"}, signature)


def test_endorsement_binds_document_review_signer_and_key():
    private, public = _keypair()
    _, _, fingerprint = parse_signer_public_key(public)
    envelope, participant, decision = _context()
    payload = endorsement_payload(
        envelope=envelope, participant=participant, decision=decision,
        fingerprint=fingerprint, nonce="new-endorsement-nonce-123456789",
    )
    signature = _sign(private, payload)
    assert verify_detached(public, payload, signature)
    for field, modified in (
        ("document_sha256", "f" * 64),
        ("review_consent_sha256", "d" * 64),
        ("participant_id", 99),
        ("signing_order", 2),
        ("organization_id", 100),
        ("nonce", "different-endorsement-nonce-123456789"),
    ):
        assert not verify_detached(public, {**payload, field: modified}, signature)


def test_unrelated_or_malformed_key_cannot_endorse():
    first_private, first_public = _keypair()
    second_private, second_public = _keypair()
    envelope, participant, decision = _context()
    _, _, fingerprint = parse_signer_public_key(first_public)
    payload = endorsement_payload(
        envelope=envelope, participant=participant, decision=decision,
        fingerprint=fingerprint, nonce="nonce-bound-to-doc-123456789",
    )
    assert not verify_detached(second_public, payload, _sign(first_private, payload))
    assert not verify_detached(first_public, payload, _sign(second_private, payload))
    assert not verify_detached(first_public, payload, "not-base64!")


def test_no_private_key_material_is_supported_in_registration():
    private, public = _keypair()
    secret_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    with pytest.raises(ValueError):
        parse_signer_public_key(secret_pem)


def test_unacknowledged_decision_not_signable():
    _, public = _keypair()
    _, _, fingerprint = parse_signer_public_key(public)
    envelope, participant, decision = _context()
    decision.decision = "declined"
    with pytest.raises(ValueError):
        endorsement_payload(
            envelope=envelope, participant=participant, decision=decision,
            fingerprint=fingerprint, nonce="signer-decline-nonce-123456789",
        )
