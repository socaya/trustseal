"""Real Ed25519 stamp attestation signing, tamper and custody tests."""
from datetime import datetime
from types import SimpleNamespace

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app.services.stamp_attestation import (
    SCHEMA, stamp_payload, issue_attestation, verify_attestation,
    trusted_stamp_key, attestation_digest,
)
from app.services.signing_receipts import public_key_id
import pytest


def _data():
    now = datetime(2026, 11, 13, 16, 0, 0)
    stamp = SimpleNamespace(
        id=7, organization_id=10, code="LEGAL-007", name="Legal Registry",
        custodian_id=11, approved_by_id=13, approved_at=now,
    )
    application = SimpleNamespace(
        id=15, stamp_id=7, organization_id=10,
        finalized_pdf_id=21, source_sha256="a" * 64,
        evidence_sha256="b" * 64, requested_by_id=11,
        reason="Approved organizational issue",
        decided_by_id=13, decided_at=now, status="approved",
    )
    pdf = SimpleNamespace(
        id=21, organization_id=10, output_sha256="a" * 64,
        evidence_sha256="b" * 64, certificate_sha256="c" * 64,
    )
    return stamp, application, pdf, now


def test_stamp_attestation_cryptographically_verifies_and_binds_pdf():
    stamp, request, pdf, moment = _data()
    key = Ed25519PrivateKey.generate()
    payload = stamp_payload(stamp, request, pdf, operator_id=19, issued_at=moment)
    assert payload["schema"] == SCHEMA
    proof = issue_attestation(payload, key)
    assert verify_attestation(proof, key.public_key())
    assert len(attestation_digest(proof)) == 64
    assert not verify_attestation(proof, Ed25519PrivateKey.generate().public_key())
    proof["payload"]["finalized_pdf_sha256"] = "d" * 64
    assert not verify_attestation(proof, key.public_key())


def test_stamp_issuance_requires_independent_approved_document_binding():
    stamp, application, pdf, moment = _data()
    application.status = "pending"
    with pytest.raises(ValueError):
        stamp_payload(stamp, application, pdf, 19, moment)
    application.status = "approved"
    pdf.output_sha256 = "e" * 64
    with pytest.raises(ValueError):
        stamp_payload(stamp, application, pdf, 19, moment)


def test_stamp_key_registry_fail_closed():
    key = Ed25519PrivateKey.generate()
    with pytest.raises(ValueError, match="Unknown"):
        trusted_stamp_key({}, public_key_id(key.public_key()))


def test_reject_attestation_with_wrong_schema_or_algorithm():
    stamp, application, pdf, moment = _data()
    key = Ed25519PrivateKey.generate()
    payload = stamp_payload(stamp, application, pdf, 19, moment)
    with pytest.raises(ValueError):
        issue_attestation({**payload, "schema": "invalid"}, key)
    signed = issue_attestation(payload, key)
    signed["algorithm"] = "none"
    assert not verify_attestation(signed, key.public_key())
