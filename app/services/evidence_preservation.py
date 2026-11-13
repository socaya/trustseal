"""Fail-closed artifact preservation and detached integrity checkpoint logic.

No destructive purge is exposed. This is signed *platform evidence* and not
a trusted timestamp, independently anchored ledger, or certificate revocation
record. Publication of a checkpoint to external WORM storage is a future gate.
"""
import base64
import hashlib
import re
from datetime import datetime, timedelta

from cryptography.exceptions import InvalidSignature

from app.services.signing_receipts import (
    canonical_bytes, load_public_key, public_key_id,
)
from app.models.pdf_finalization import FinalizedPdf
from app.models.stamped_pdf import StampedPdf
from app.services.documents.private_storage import check_object_digest
from app.services.platform_pdf_seal import inspect_signed_pdf


SCHEMA = "trustseal.evidence-checkpoint.v1"
KINDS = {"finalized_pdf": FinalizedPdf, "stamped_pdf": StampedPdf}


def artifact_for(kind, artifact_id, organization_id):
    if kind not in KINDS or type(artifact_id) is not int or artifact_id < 1:
        raise ValueError("Invalid evidence artifact")
    record = KINDS[kind].query.filter_by(
        id=artifact_id, organization_id=organization_id
    ).first()
    if record is None:
        raise ValueError("Artifact is not accessible")
    return record


def verify_artifact(record, kind, config):
    if kind == "stamped_pdf":
        # A stamp derivative requires the signed original PDF, immutable
        # issuance approval and complete stamp-design provenance as well.
        from app.extensions import db
        from app.models.stamp_custody import (
            ManagedStamp, StampApplication, StampAttestation,
        )
        from app.blueprints.estamp.stamped_pdf_api import _verify_lineage
        receipt = db.session.get(StampAttestation, record.stamp_attestation_id)
        application = (
            db.session.get(StampApplication, receipt.application_id)
            if receipt is not None else None
        )
        stamp = (
            db.session.get(ManagedStamp, receipt.stamp_id)
            if receipt is not None else None
        )
        original = db.session.get(FinalizedPdf, record.source_finalized_pdf_id)
        if any(item is None for item in (receipt, application, stamp, original)):
            raise ValueError("Stamp preservation approval lineage missing")
        path, _provenance = _verify_lineage(
            record, receipt, application, stamp, original
        )
        return hashlib.sha256(path.read_bytes()).hexdigest()
    path = check_object_digest(record.object_key, record.output_sha256, config)
    data = path.read_bytes()
    status = inspect_signed_pdf(
        data, config,
        expected_evidence_sha256=(
            record.evidence_sha256 if kind == "finalized_pdf"
            else record.signed_evidence_sha256
        ),
        expected_certificate_sha256=record.certificate_sha256,
        evidence_purpose="review" if kind == "finalized_pdf" else "stamp",
    )
    if not status["overall_valid"]:
        raise ValueError("Artifact certificate validation failed")
    return hashlib.sha256(data).hexdigest()


def protection_status(retention, active_holds, now=None):
    now = now or datetime.utcnow()
    return {
        "retain_until": retention.retain_until.isoformat() + "Z",
        "retention_active": retention.retain_until > now,
        "active_legal_holds": active_holds,
        "deletion_permitted": False,
    }


def checkpoint_payload(retention, operator_id, checked_at):
    return {
        "schema": SCHEMA,
        "assurance": "platform_signed_integrity_observation_only",
        "retention_id": retention.id,
        "organization_id": retention.organization_id,
        "artifact_type": retention.artifact_type,
        "artifact_id": retention.artifact_id,
        "artifact_sha256": retention.artifact_sha256,
        "retain_until": retention.retain_until.isoformat(timespec="microseconds") + "Z",
        "operator_id": operator_id,
        "checked_at": checked_at.isoformat(timespec="microseconds") + "Z",
    }


def sign_checkpoint(payload, private_key):
    if payload.get("schema") != SCHEMA:
        raise ValueError("Unsupported checkpoint version")
    return {
        "payload": payload,
        "algorithm": "Ed25519",
        "key_id": public_key_id(private_key.public_key()),
        "signature": base64.b64encode(
            private_key.sign(canonical_bytes(payload))
        ).decode("ascii"),
    }


def verify_checkpoint(evidence, key):
    try:
        if (evidence["algorithm"] != "Ed25519"
                or evidence["payload"].get("schema") != SCHEMA
                or evidence["key_id"] != public_key_id(key)):
            return False
        signature = base64.b64decode(evidence["signature"], validate=True)
        if len(signature) != 64:
            return False
        key.verify(signature, canonical_bytes(evidence["payload"]))
        return True
    except (KeyError, ValueError, TypeError, InvalidSignature):
        return False


def trusted_checkpoint_key(config, key_id):
    import json
    if not isinstance(key_id, str) or not re.fullmatch(
        r"ed25519-sha256:[0-9a-f]{64}", key_id
    ):
        raise ValueError("Invalid checkpoint signing key fingerprint")
    candidates = {}
    current = config.get("EVIDENCE_CHECKPOINT_PUBLIC_KEY")
    if current:
        key = load_public_key(current)
        candidates[public_key_id(key)] = key
    historical = config.get("EVIDENCE_CHECKPOINT_TRUSTED_KEYS_JSON")
    if historical:
        registry = json.loads(historical)
        if not isinstance(registry, dict):
            raise ValueError("Invalid checkpoint trust registry")
        for fingerprint, path in registry.items():
            if not isinstance(path, str):
                raise ValueError("Invalid checkpoint key location")
            key = load_public_key(path)
            if fingerprint != public_key_id(key):
                raise ValueError("Checkpoint key fingerprint mismatch")
            candidates[fingerprint] = key
    if key_id not in candidates:
        raise ValueError("Checkpoint signing key not trusted")
    return candidates[key_id]
