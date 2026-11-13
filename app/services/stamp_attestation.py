"""Detached Ed25519 organizational stamp-authorization attestations.

This attests an approved stamp application against a specific already-sealed
PDF; it does not alter or impress the PDF and does not confer statutory seal
status. Signing keys are kept out of the request/response and database.
"""
import base64
import hashlib
import json

from cryptography.exceptions import InvalidSignature
from app.services.signing_receipts import (
    canonical_bytes, public_key_id, load_private_key, load_public_key,
)

SCHEMA = "trustseal.governed-stamp-attestation.v1"


def stamp_payload(stamp, application, pdf, operator_id, issued_at):
    if (stamp.id != application.stamp_id
            or stamp.organization_id != application.organization_id
            or application.finalized_pdf_id != pdf.id
            or pdf.organization_id != stamp.organization_id
            or application.source_sha256 != pdf.output_sha256
            or application.evidence_sha256 != pdf.evidence_sha256
            or application.status != "approved"
            or stamp.approved_at is None
            or application.decided_at is None
            or issued_at is None):
        raise ValueError("Inconsistent or unapproved stamp attestation context")
    return {
        "schema": SCHEMA,
        "assurance": "organizational_authorization_attestation_not_pdf_impression",
        "stamp_id": stamp.id,
        "stamp_code": stamp.code,
        "stamp_name": stamp.name,
        "organization_id": stamp.organization_id,
        "custodian_id": stamp.custodian_id,
        "stamp_approved_by_id": stamp.approved_by_id,
        "stamp_approved_at": stamp.approved_at.isoformat(timespec="microseconds") + "Z",
        "application_id": application.id,
        "requested_by_id": application.requested_by_id,
        "request_reason": application.reason,
        "decided_by_id": application.decided_by_id,
        "decided_at": application.decided_at.isoformat(timespec="microseconds") + "Z",
        "finalized_pdf_id": pdf.id,
        "finalized_pdf_sha256": pdf.output_sha256,
        "review_evidence_sha256": pdf.evidence_sha256,
        "platform_seal_cert_sha256": pdf.certificate_sha256,
        "issued_by_id": operator_id,
        "issued_at": issued_at.isoformat(timespec="microseconds") + "Z",
    }


def issue_attestation(payload, private_key):
    if payload.get("schema") != SCHEMA:
        raise ValueError("Incorrect stamp evidence schema")
    return {
        "payload": payload,
        "algorithm": "Ed25519",
        "key_id": public_key_id(private_key.public_key()),
        "signature": base64.b64encode(
            private_key.sign(canonical_bytes(payload))
        ).decode("ascii"),
    }


def verify_attestation(attestation, public_key):
    try:
        if (attestation.get("algorithm") != "Ed25519"
                or attestation.get("key_id") != public_key_id(public_key)
                or attestation["payload"].get("schema") != SCHEMA):
            return False
        signature = base64.b64decode(attestation["signature"], validate=True)
        if len(signature) != 64:
            return False
        public_key.verify(signature, canonical_bytes(attestation["payload"]))
        return True
    except (InvalidSignature, TypeError, KeyError, ValueError):
        return False


def trusted_stamp_key(config, key_id):
    """Load only approved pinned key IDs, including explicitly retained keys."""
    available = {}
    current = config.get("STAMP_ATTESTATION_PUBLIC_KEY")
    if current:
        key = load_public_key(current)
        available[public_key_id(key)] = key
    historical = config.get("STAMP_ATTESTATION_TRUSTED_KEYS_JSON")
    if historical:
        mapping = json.loads(historical)
        if not isinstance(mapping, dict):
            raise ValueError("Invalid stamp trust registry")
        for fingerprint, path in mapping.items():
            if not isinstance(path, str):
                raise ValueError("Invalid trusted key path")
            key = load_public_key(path)
            if fingerprint != public_key_id(key):
                raise ValueError("Stamp trust key fingerprint mismatch")
            available[fingerprint] = key
    if key_id not in available:
        raise ValueError("Unknown stamp attestation issuer key")
    return available[key_id]


def attestation_digest(attestation):
    return hashlib.sha256(canonical_bytes(attestation)).hexdigest()
