"""Preservation checkpoint cryptographic and non-destructive policy tests."""
from datetime import datetime, timedelta
from types import SimpleNamespace

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app.services.evidence_preservation import (
    checkpoint_payload, sign_checkpoint, verify_checkpoint, protection_status,
)


def test_signed_retention_observation_rejects_alteration():
    private = Ed25519PrivateKey.generate()
    retention = SimpleNamespace(
        id=17, organization_id=4, artifact_type="finalized_pdf",
        artifact_id=9, artifact_sha256="a" * 64,
        retain_until=datetime(2036, 1, 1),
    )
    observed = datetime(2026, 11, 13, 9, 4, 3)
    payload = checkpoint_payload(retention, 11, observed)
    signed = sign_checkpoint(payload, private)
    assert verify_checkpoint(signed, private.public_key())
    assert not verify_checkpoint(signed, Ed25519PrivateKey.generate().public_key())
    signed["payload"]["artifact_sha256"] = "b" * 64
    assert not verify_checkpoint(signed, private.public_key())


def test_retention_policy_never_implicitly_permits_deletion():
    now = datetime(2026, 11, 13)
    future = SimpleNamespace(retain_until=now + timedelta(days=400))
    expired = SimpleNamespace(retain_until=now - timedelta(days=10))
    assert protection_status(future, 0, now)["deletion_permitted"] is False
    assert protection_status(expired, 0, now)["deletion_permitted"] is False
    assert protection_status(expired, 1, now)["active_legal_holds"] == 1


def test_checkpoint_payload_binds_custodian_and_artifact():
    retention = SimpleNamespace(
        id=1, organization_id=2, artifact_type="stamped_pdf",
        artifact_id=3, artifact_sha256="f" * 64,
        retain_until=datetime(2032, 1, 1),
    )
    payload = checkpoint_payload(retention, 17, datetime(2026, 11, 13))
    assert payload["operator_id"] == 17
    assert payload["artifact_type"] == "stamped_pdf"
    assert payload["artifact_id"] == 3
    assert payload["artifact_sha256"] == "f" * 64
