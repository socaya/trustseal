#!/usr/bin/env python3
"""Offline verification of a TrustSeal signed integrity checkpoint.

The trust anchor must be independently obtained and pinned. This verifies a
platform observation of an artifact hash at a recorded time, NOT the current
existence of its PDF bytes or an accredited timestamp.

Example:
  python examples/verify_checkpoint_offline.py --evidence receipt.json \
    --public-key trusted.pem --fingerprint ed25519-sha256:<64hex>
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SCHEMA = "trustseal.evidence-checkpoint.v1"


def verify_file(evidence_path, public_key_path, expected_fingerprint):
    evidence_file = Path(evidence_path)
    public_file = Path(public_key_path)
    if (not evidence_file.is_file() or evidence_file.stat().st_size > 65536
            or not public_file.is_file() or public_file.stat().st_size > 8192):
        raise ValueError("Evidence or trust key exceeds safe size limit")
    evidence = json.loads(evidence_file.read_text(encoding="utf-8"))
    if not isinstance(evidence, dict) or set(evidence) != {
        "payload", "algorithm", "key_id", "signature"
    }:
        raise ValueError("Invalid detached evidence structure")
    payload = evidence["payload"]
    if (not isinstance(payload, dict) or payload.get("schema") != SCHEMA
            or payload.get("assurance") != "platform_signed_integrity_observation_only"
            or evidence["algorithm"] != "Ed25519"):
        raise ValueError("Invalid checkpoint assurance or algorithm")
    key = serialization.load_pem_public_key(public_file.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("Trusted key must be Ed25519")
    raw = key.public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    calculated = "ed25519-sha256:" + hashlib.sha256(raw).hexdigest()
    if (evidence["key_id"] != calculated
            or expected_fingerprint != calculated):
        raise ValueError("Checkpoint issuer differs from independently pinned key")
    signature = base64.b64decode(evidence["signature"], validate=True)
    if len(signature) != 64:
        raise ValueError("Invalid Ed25519 signature length")
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    key.verify(signature, canonical)
    return {
        "valid": True, "artifact_type": payload["artifact_type"],
        "artifact_id": payload["artifact_id"],
        "artifact_sha256": payload["artifact_sha256"],
        "checked_at": payload["checked_at"],
        "key_id": calculated,
        "assurance": payload["assurance"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, help="Exported detached checkpoint JSON")
    parser.add_argument("--public-key", required=True, help="Independently trusted PEM key")
    parser.add_argument("--fingerprint", required=True, help="Pinned Ed25519 key fingerprint")
    options = parser.parse_args()
    try:
        result = verify_file(
            options.evidence, options.public_key, options.fingerprint
        )
    except Exception:
        parser.exit(1, "Checkpoint validation failed\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
