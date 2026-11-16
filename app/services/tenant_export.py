"""Signed per-tenant data export (GDPR Article 20).

Produces a JSON document that contains every row tied to a given
organization, arranged by table. The bundle is signed with the
operator's Ed25519 key (when configured) so the recipient can
verify provenance offline.

The service walks a conservative allowlist of tables rather than
reflecting on the SQLAlchemy metadata so a future schema change
cannot silently widen the export. Add a new table to
:data:`EXPORTED_TABLES` when it should appear in the output.

Fields that reference other tenants' resources (`created_by_id`
pointing at a cross-org user, for example) are not scrubbed — the
export is intended for the tenant's own records and the audit
chain. Downstream consumers that need PII minimisation should
transform the bundle themselves.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Iterable, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from flask import current_app

from app.extensions import db


# ---------------------------------------------------------- tables


# (table_name, filter column) pairs. Every row where the filter
# column matches the exported organization is included.
EXPORTED_TABLES: tuple[tuple[str, str], ...] = (
    ("organizations", "id"),
    ("users", "organization_id"),
    ("user_invitations", "organization_id"),
    ("teams", "organization_id"),
    ("delegations", "organization_id"),
    ("documents", "organization_id"),
    ("document_blobs_via_document", "__custom__"),
    ("signing_envelopes", "organization_id"),
    ("envelope_participants_via_envelope", "__custom__"),
    ("envelope_fields_via_envelope", "__custom__"),
    ("envelope_routing_rules_via_envelope", "__custom__"),
    ("signer_decisions_via_envelope", "__custom__"),
    ("signer_invitations_via_envelope", "__custom__"),
    ("signer_appearances_via_envelope", "__custom__"),
    ("review_receipts", "organization_id"),
    ("finalized_pdfs", "organization_id"),
    ("managed_stamps", "organization_id"),
    ("stamp_applications", "organization_id"),
    ("stamp_attestations", "organization_id"),
    ("stamped_pdfs", "organization_id"),
    ("evidence_retentions", "organization_id"),
    ("evidence_legal_holds_via_retention", "__custom__"),
    ("evidence_checkpoints_via_retention", "__custom__"),
    ("evidence_timestamps", "organization_id"),
    ("validation_dossiers", "organization_id"),
    ("audit_chain_anchors", "organization_id"),
    ("security_events", "organization_id"),
    ("usage_ledger_entries", "organization_id"),
    ("bulk_ingest_batches", "organization_id"),
    ("clauses", "organization_id"),
    ("saml_providers", "organization_id"),
    ("webhook_endpoints", "organization_id"),
    ("plan_entitlements_via_subscription", "__custom__"),
)


@dataclass(frozen=True)
class SignedExport:
    bundle: dict
    bundle_sha256: str
    signature_hex: Optional[str]
    signing_key_fingerprint: Optional[str]


class TenantExportError(RuntimeError):
    """Raised when export cannot be produced for policy reasons."""


# ---------------------------------------------------------- JSON helpers


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    raise TypeError(f"not_json_serialisable:{type(value).__name__}")


def _rows_to_dicts(rows: Iterable[Any]) -> list[dict]:
    return [dict(row._mapping) for row in rows]


# ---------------------------------------------------------- collectors


def _collect_direct(organization_id: int, table: str, column: str) -> list[dict]:
    from sqlalchemy import text

    result = db.session.execute(
        text(f'SELECT * FROM "{table}" WHERE "{column}" = :org'),
        {"org": organization_id},
    )
    return _rows_to_dicts(result)


def _collect_custom(organization_id: int, key: str) -> list[dict]:
    from sqlalchemy import text

    if key == "document_blobs_via_document":
        q = text(
            "SELECT b.* FROM document_blobs b "
            "JOIN documents d ON d.id = b.document_id "
            "WHERE d.organization_id = :org"
        )
    elif key == "envelope_participants_via_envelope":
        q = text(
            "SELECT p.* FROM envelope_participants p "
            "JOIN signing_envelopes e ON e.id = p.envelope_id "
            "WHERE e.organization_id = :org"
        )
    elif key == "envelope_fields_via_envelope":
        q = text(
            "SELECT f.* FROM envelope_fields f "
            "JOIN signing_envelopes e ON e.id = f.envelope_id "
            "WHERE e.organization_id = :org"
        )
    elif key == "envelope_routing_rules_via_envelope":
        q = text(
            "SELECT r.* FROM envelope_routing_rules r "
            "JOIN signing_envelopes e ON e.id = r.envelope_id "
            "WHERE e.organization_id = :org"
        )
    elif key == "signer_decisions_via_envelope":
        q = text(
            "SELECT d.* FROM signer_decisions d "
            "JOIN signing_envelopes e ON e.id = d.envelope_id "
            "WHERE e.organization_id = :org"
        )
    elif key == "signer_invitations_via_envelope":
        q = text(
            "SELECT i.* FROM signer_invitations i "
            "JOIN signing_envelopes e ON e.id = i.envelope_id "
            "WHERE e.organization_id = :org"
        )
    elif key == "evidence_legal_holds_via_retention":
        q = text(
            "SELECT h.* FROM evidence_legal_holds h "
            "JOIN evidence_retentions r ON r.id = h.retention_id "
            "WHERE r.organization_id = :org"
        )
    elif key == "evidence_checkpoints_via_retention":
        q = text(
            "SELECT c.* FROM evidence_checkpoints c "
            "JOIN evidence_retentions r ON r.id = c.retention_id "
            "WHERE r.organization_id = :org"
        )
    elif key == "plan_entitlements_via_subscription":
        # Plan entitlements are tenant-scoped indirectly via the
        # organization's subscription.
        q = text(
            "SELECT pe.* FROM plan_entitlements pe "
            "JOIN subscriptions s ON s.plan_id = pe.plan_id "
            "JOIN organizations o ON o.subscription_id = s.id "
            "WHERE o.id = :org"
        )
    elif key == "signer_appearances_via_envelope":
        q = text(
            "SELECT a.* FROM signer_appearances a "
            "JOIN signing_envelopes e ON e.id = a.envelope_id "
            "WHERE e.organization_id = :org"
        )
    else:
        return []
    result = db.session.execute(q, {"org": organization_id})
    return _rows_to_dicts(result)


# ---------------------------------------------------------- signing


def _load_signing_key() -> Optional[tuple[ed25519.Ed25519PrivateKey, str]]:
    """Load the operator Ed25519 key when configured.

    The ``TENANT_EXPORT_SIGNING_KEY`` config holds a PEM-encoded
    private key. Returns ``(key, fingerprint)`` or ``None`` when
    not configured — the export still proceeds but the signature
    fields are null so operators can see the bundle was unsigned.
    """
    pem = current_app.config.get("TENANT_EXPORT_SIGNING_KEY")
    if not pem:
        return None
    try:
        key = serialization.load_pem_private_key(
            pem.encode("ascii"), password=None
        )
    except Exception as exc:
        raise TenantExportError("signing_key_invalid") from exc
    if not isinstance(key, ed25519.Ed25519PrivateKey):
        raise TenantExportError("signing_key_not_ed25519")
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    fingerprint = hashlib.sha256(public).hexdigest()
    return key, fingerprint


# ---------------------------------------------------------- public API


def export_tenant(organization_id: int) -> SignedExport:
    """Return the signed JSON bundle for ``organization_id``."""
    if not isinstance(organization_id, int):
        raise TenantExportError("organization_id_invalid")
    bundle: dict[str, Any] = {
        "bundle_format": "trustseal-tenant-export-v1",
        "organization_id": organization_id,
        "exported_at": datetime.utcnow().isoformat(),
        "tables": {},
    }
    for table, column in EXPORTED_TABLES:
        if column == "__custom__":
            rows = _collect_custom(organization_id, table)
            key = table.rsplit("_via_", 1)[0]
        else:
            rows = _collect_direct(organization_id, table, column)
            key = table
        bundle["tables"][key] = rows
    canonical = json.dumps(
        bundle,
        default=_json_default,
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
    return SignedExport(
        bundle=bundle,
        bundle_sha256=bundle_sha,
        signature_hex=signature_hex,
        signing_key_fingerprint=fingerprint,
    )


def verify_export(
    bundle: dict,
    signature_hex: str,
    *,
    public_key_pem: str,
) -> bool:
    """Verify a signed export bundle against ``public_key_pem``.

    Returns True when the signature matches the canonical JSON of
    ``bundle``; False otherwise. Never raises on signature failure.
    """
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
        default=_json_default,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    try:
        public.verify(bytes.fromhex(signature_hex), canonical)
    except (InvalidSignature, ValueError):
        return False
    return True
