"""Signed audit-chain slice export (M3).

An operator exports a half-open window of the ``security_events``
chain for an auditor. The service:

* Walks the chain in id order within the window.
* Carries the ``anchor_prev_hash`` — the ``prev_event_hash`` of the
  first row in the window — so the auditor can continue hash
  verification from an external anchor.
* Canonical-JSON-serialises the slice and signs the serialisation
  with the operator Ed25519 key when configured.

The result is a self-contained bundle: the auditor can re-run
``_canonical_event`` (documented alongside ``app.services.audit_chain``)
over each event in order and confirm every ``event_hash`` matches
``sha256(prev + canonical)``.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from flask import current_app

from app.extensions import db
from app.models.event_delivery import SecurityEvent


class AuditChainExportError(RuntimeError):
    """Raised for policy failures during export."""


@dataclass(frozen=True)
class SignedAuditSlice:
    bundle: dict
    bundle_sha256: str
    signature_hex: Optional[str]
    signing_key_fingerprint: Optional[str]


DEFAULT_MAX_ROWS = 10_000


def _to_dict(event: SecurityEvent) -> dict:
    return {
        "id": event.id,
        "organization_id": event.organization_id,
        "actor_id": event.actor_id,
        "action": event.action,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "outcome": event.outcome,
        "correlation_id": event.correlation_id,
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "prev_event_hash": event.prev_event_hash,
        "event_hash": event.event_hash,
    }


def _load_signing_key() -> Optional[tuple[ed25519.Ed25519PrivateKey, str]]:
    pem = current_app.config.get("AUDIT_EXPORT_SIGNING_KEY") or current_app.config.get(
        "TENANT_EXPORT_SIGNING_KEY"
    )
    if not pem:
        return None
    try:
        key = serialization.load_pem_private_key(
            pem.encode("ascii"), password=None
        )
    except Exception as exc:
        raise AuditChainExportError("signing_key_invalid") from exc
    if not isinstance(key, ed25519.Ed25519PrivateKey):
        raise AuditChainExportError("signing_key_not_ed25519")
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    fingerprint = hashlib.sha256(public).hexdigest()
    return key, fingerprint


def export_slice(
    *,
    organization_id: Optional[int] = None,
    from_id: Optional[int] = None,
    to_id: Optional[int] = None,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> SignedAuditSlice:
    """Return the signed slice.

    * ``organization_id`` restricts the slice to a tenant when
      supplied; operators auditing cross-tenant can leave it None.
    * ``from_id`` + ``to_id`` are inclusive bounds. Defaults to the
      full chain (bounded by ``max_rows``).
    """
    if max_rows <= 0 or max_rows > 100_000:
        raise AuditChainExportError("max_rows_out_of_range")
    query = SecurityEvent.query.order_by(SecurityEvent.id.asc())
    if organization_id is not None:
        query = query.filter(SecurityEvent.organization_id == organization_id)
    if from_id is not None:
        query = query.filter(SecurityEvent.id >= int(from_id))
    if to_id is not None:
        query = query.filter(SecurityEvent.id <= int(to_id))
    rows = query.limit(max_rows + 1).all()
    truncated = len(rows) > max_rows
    rows = rows[:max_rows]
    anchor_prev_hash: Optional[str] = None
    if rows:
        anchor_prev_hash = rows[0].prev_event_hash
    bundle = {
        "bundle_format": "trustseal-audit-chain-slice-v1",
        "exported_at": datetime.utcnow().isoformat(),
        "organization_id": organization_id,
        "requested_from_id": from_id,
        "requested_to_id": to_id,
        "anchor_prev_hash": anchor_prev_hash,
        "events": [_to_dict(r) for r in rows],
        "truncated": truncated,
        "max_rows": max_rows,
        "row_count": len(rows),
    }
    canonical = json.dumps(
        bundle,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    bundle_sha = hashlib.sha256(canonical).hexdigest()
    signing = _load_signing_key()
    signature_hex: Optional[str] = None
    fingerprint: Optional[str] = None
    if signing is not None:
        key, fingerprint = signing
        signature_hex = key.sign(canonical).hex()
    return SignedAuditSlice(
        bundle=bundle,
        bundle_sha256=bundle_sha,
        signature_hex=signature_hex,
        signing_key_fingerprint=fingerprint,
    )


def verify_slice(
    bundle: dict, signature_hex: str, *, public_key_pem: str
) -> bool:
    try:
        public = serialization.load_pem_public_key(
            public_key_pem.encode("ascii")
        )
    except Exception:
        return False
    if not isinstance(public, ed25519.Ed25519PublicKey):
        return False
    canonical = json.dumps(
        bundle,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    try:
        public.verify(bytes.fromhex(signature_hex), canonical)
    except (InvalidSignature, ValueError):
        return False
    return True
