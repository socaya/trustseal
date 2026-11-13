"""Offline checkpoint verifier works without a connected TrustSeal instance."""
import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from examples.verify_checkpoint_offline import verify_file
from app.services.evidence_preservation import checkpoint_payload, sign_checkpoint


def test_pinned_offline_checkpoint_signature_and_tamper_rejection(tmp_path):
    private = Ed25519PrivateKey.generate()
    public_path = tmp_path / "trusted.pem"
    public_path.write_bytes(private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    record = SimpleNamespace(
        id=5, organization_id=3, artifact_type="stamped_pdf",
        artifact_id=12, artifact_sha256="b" * 64,
        retain_until=datetime(2031, 12, 31),
    )
    signed = sign_checkpoint(
        checkpoint_payload(record, 7, datetime(2026, 11, 13)),
        private,
    )
    receipt_file = tmp_path / "checkpoint.json"
    receipt_file.write_text(json.dumps(signed))
    verified = verify_file(
        receipt_file, public_path, signed["key_id"],
    )
    assert verified["valid"] is True
    assert verified["artifact_sha256"] == "b" * 64
    with pytest.raises(ValueError, match="pinned"):
        verify_file(
            receipt_file, public_path,
            "ed25519-sha256:" + "f" * 64,
        )
    signed["payload"]["artifact_sha256"] = "f" * 64
    receipt_file.write_text(json.dumps(signed))
    with pytest.raises(Exception):
        verify_file(receipt_file, public_path, signed["key_id"])
