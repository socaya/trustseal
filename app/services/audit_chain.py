"""Chained-hash integrity for security events.

Every :class:`SecurityEvent` row carries two columns:

* ``prev_event_hash`` — ``event_hash`` of the predecessor in the same
  tenant, or ``"GENESIS"`` for the first row.
* ``event_hash`` — ``SHA-256(prev_event_hash || canonical_payload)``.

The canonical payload is a stable JSON serialisation of the fields a
reviewer cares about. Adding a new field to the serialisation changes
every subsequent hash — callers who need to version the canonical
form should add a ``chain_version`` column and verify per-version.

This module exposes:

* :func:`attach_hashes_before_commit` — a SQLAlchemy event hook that
  computes the hash of each new ``SecurityEvent`` at flush time so
  callers never have to think about it.
* :func:`verify_chain(tenant_id)` — walks the tenant's events ordered
  by id, recomputes each hash, and returns a :class:`ChainReport`.
* :func:`backfill(tenant_id)` — one-shot helper that assigns hashes to
  pre-existing rows written before this migration.

Threats this mitigates:

* **T3** (threat-model.md) — audit-event chain tampering. A row
  inserted, re-ordered, deleted, or mutated breaks the chain because
  ``prev_event_hash`` no longer matches the recomputed ``event_hash``
  of the predecessor.

Not mitigated:

* An attacker with DB-write access can rewrite the full chain in
  place. Pair this with the signed ``EvidenceCheckpoint`` stream to
  pin chain prefixes to an independently signed statement.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import event

from app.extensions import db
from app.models.event_delivery import SecurityEvent

GENESIS = "GENESIS"


@dataclass(frozen=True)
class ChainBreak:
    """Describes a single break in the chain.

    ``at_id`` is the event id where the recomputed hash no longer
    matches the stored hash; ``expected`` and ``found`` help a
    reviewer see whether a specific field was mutated.
    """

    at_id: int
    expected: str
    found: str
    reason: str


@dataclass(frozen=True)
class ChainReport:
    tenant_id: int
    checked: int
    unhashed: int
    breaks: tuple[ChainBreak, ...]

    def ok(self) -> bool:
        return not self.breaks and self.unhashed == 0


# ---------------------------------------------------------------- canonical


def canonical_payload(event: SecurityEvent) -> bytes:
    """Return the bytes the hash covers.

    Keep this function monotonic: fields may only be added, never
    renamed or reordered. New fields change the hash of every row
    issued afterwards.
    """
    payload = {
        "organization_id": event.organization_id,
        "actor_id": event.actor_id,
        "action": event.action,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "outcome": event.outcome,
        "correlation_id": event.correlation_id,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def compute_hash(prev_hash: str, event: SecurityEvent) -> str:
    base = (prev_hash + ":").encode("ascii") + canonical_payload(event)
    return hashlib.sha256(base).hexdigest()


def _latest_hash(tenant_id: int, before_id: int | None = None) -> str:
    """Return the chain tip for ``tenant_id`` before ``before_id``.

    Used both by the pre-flush listener (``before_id=None``) and by the
    verifier when it needs to re-anchor at a specific position.
    """
    query = SecurityEvent.query.filter(
        SecurityEvent.organization_id == tenant_id,
        SecurityEvent.event_hash.isnot(None),
    )
    if before_id is not None:
        query = query.filter(SecurityEvent.id < before_id)
    row = query.order_by(SecurityEvent.id.desc()).first()
    return row.event_hash if row is not None else GENESIS


# ---------------------------------------------------------------- hooks


def attach_hashes_before_flush(session, _flush_context, _instances) -> None:
    """Session-flush hook: fill prev/event hashes on pending SecurityEvent rows.

    Running at ``before_flush`` lets us chain multiple same-tenant
    events added to the same session in one go — their ids aren't
    assigned yet, so we respect the order they were added to the
    session. For each tenant we anchor at the current committed tip
    and extend forward.
    """
    pending = [obj for obj in session.new if isinstance(obj, SecurityEvent)]
    if not pending:
        return
    # Preserve add-order within the same tenant.
    by_tenant: dict[int | None, list[SecurityEvent]] = {}
    for obj in pending:
        by_tenant.setdefault(obj.organization_id, []).append(obj)
    for tenant_id, events in by_tenant.items():
        if tenant_id is None:
            tip = GENESIS
        else:
            tip = _latest_hash(tenant_id)
        for obj in events:
            if obj.event_hash is not None:
                tip = obj.event_hash
                continue
            if obj.created_at is None:
                from datetime import datetime

                obj.created_at = datetime.utcnow()
            obj.prev_event_hash = tip
            obj.event_hash = compute_hash(tip, obj)
            tip = obj.event_hash


_HOOK_INSTALLED = False


def register_chain_hook(app) -> None:
    """Install the pre-flush listener on the Flask-SQLAlchemy Session class.

    We target the Flask-SQLAlchemy Session subclass directly so the
    hook fires regardless of how callers scope their session. The
    ``propagate=True`` flag covers any further subclassing by test
    harnesses. Idempotent.
    """
    global _HOOK_INSTALLED
    if _HOOK_INSTALLED:
        return
    from flask_sqlalchemy.session import Session as FlaskSqlalchemySession

    event.listen(
        FlaskSqlalchemySession,
        "before_flush",
        attach_hashes_before_flush,
        propagate=True,
    )
    _HOOK_INSTALLED = True


# ---------------------------------------------------------------- verifier


def verify_chain(
    tenant_id: int,
    *,
    batch_size: int = 500,
    anchor_trusted_key_resolver=None,
) -> ChainReport:
    """Walk ``tenant_id``'s security events and recompute each hash.

    The internal chained-hash probe catches tampering that preserves
    neither a row's content nor its position. To catch a DB-level
    rewrite that *does* preserve the chain shape, pass
    ``anchor_trusted_key_resolver(key_id) -> PublicKey``. Every
    :class:`AuditChainAnchor` is then verified: its signature must
    check against the resolved public key, and the recomputed chain
    tip at the anchor's ``anchor_event_id`` must match the signed
    ``chain_tip_hash``. Any mismatch is surfaced as a
    :class:`ChainBreak`.

    Returns a :class:`ChainReport`. The function is read-only.
    """
    breaks: list[ChainBreak] = []
    checked = 0
    unhashed = 0
    last_id = 0
    tip = GENESIS
    tip_at_event: dict[int, str] = {}
    while True:
        batch: Iterable[SecurityEvent] = (
            SecurityEvent.query.filter(
                SecurityEvent.organization_id == tenant_id,
                SecurityEvent.id > last_id,
            )
            .order_by(SecurityEvent.id.asc())
            .limit(batch_size)
            .all()
        )
        batch = list(batch)
        if not batch:
            break
        for row in batch:
            checked += 1
            last_id = row.id
            if row.event_hash is None:
                unhashed += 1
                tip_at_event[row.id] = tip
                continue
            if row.prev_event_hash != tip:
                breaks.append(
                    ChainBreak(
                        at_id=row.id,
                        expected=tip,
                        found=row.prev_event_hash or GENESIS,
                        reason="prev_event_hash does not match predecessor",
                    )
                )
            expected = compute_hash(row.prev_event_hash or GENESIS, row)
            if expected != row.event_hash:
                breaks.append(
                    ChainBreak(
                        at_id=row.id,
                        expected=expected,
                        found=row.event_hash,
                        reason="event_hash does not match recomputed payload",
                    )
                )
            tip = row.event_hash
            tip_at_event[row.id] = tip
    if anchor_trusted_key_resolver is not None:
        for anchor_break in _verify_anchors(
            tenant_id, tip_at_event, anchor_trusted_key_resolver
        ):
            breaks.append(anchor_break)
    return ChainReport(
        tenant_id=tenant_id,
        checked=checked,
        unhashed=unhashed,
        breaks=tuple(breaks),
    )


# ---------------------------------------------------------------- backfill


def backfill(tenant_id: int, *, batch_size: int = 500) -> int:
    """Assign chain hashes to rows that pre-date this migration.

    Returns the number of rows updated. Idempotent: running against an
    already-hashed tenant is a no-op.
    """
    tip = GENESIS
    hashed = 0
    last_id = 0
    while True:
        batch = (
            SecurityEvent.query.filter(
                SecurityEvent.organization_id == tenant_id,
                SecurityEvent.id > last_id,
            )
            .order_by(SecurityEvent.id.asc())
            .limit(batch_size)
            .all()
        )
        if not batch:
            break
        for row in batch:
            last_id = row.id
            if row.event_hash is not None:
                tip = row.event_hash
                continue
            row.prev_event_hash = tip
            row.event_hash = compute_hash(tip, row)
            tip = row.event_hash
            hashed += 1
        db.session.commit()
    return hashed


# ---------------------------------------------------------------- anchoring

ANCHOR_SCHEMA = "trustseal.audit-chain-anchor.v1"


def _anchor_payload(
    tenant_id: int | None,
    anchor_event_id: int | None,
    chain_tip_hash: str,
    operator_id: int,
    created_at,
) -> dict:
    return {
        "schema": ANCHOR_SCHEMA,
        "assurance": "platform_signed_audit_chain_observation_only",
        "organization_id": tenant_id,
        "anchor_event_id": anchor_event_id,
        "chain_tip_hash": chain_tip_hash,
        "operator_id": operator_id,
        "created_at": created_at.isoformat(timespec="microseconds") + "Z",
    }


def anchor_chain(
    tenant_id: int,
    *,
    operator_id: int,
    private_key,
) -> "AuditChainAnchor":
    """Snapshot the current chain tip for ``tenant_id`` and sign it.

    The returned row is persisted but not committed; the caller is
    responsible for the surrounding transaction so a failed anchor
    does not leave half-written state.
    """
    import base64

    from app.models.audit_chain_anchor import AuditChainAnchor
    from app.services.signing_receipts import canonical_bytes, public_key_id

    latest = (
        SecurityEvent.query.filter(
            SecurityEvent.organization_id == tenant_id,
            SecurityEvent.event_hash.isnot(None),
        )
        .order_by(SecurityEvent.id.desc())
        .first()
    )
    if latest is None:
        chain_tip_hash = GENESIS
        anchor_event_id = None
    else:
        chain_tip_hash = latest.event_hash
        anchor_event_id = latest.id
    from datetime import datetime

    now = datetime.utcnow()
    payload = _anchor_payload(
        tenant_id=tenant_id,
        anchor_event_id=anchor_event_id,
        chain_tip_hash=chain_tip_hash,
        operator_id=operator_id,
        created_at=now,
    )
    signature = base64.b64encode(
        private_key.sign(canonical_bytes(payload))
    ).decode("ascii")
    row = AuditChainAnchor(
        organization_id=tenant_id,
        anchor_event_id=anchor_event_id,
        chain_tip_hash=chain_tip_hash,
        payload=payload,
        algorithm="Ed25519",
        key_id=public_key_id(private_key.public_key()),
        signature=signature,
        operator_id=operator_id,
        created_at=now,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _verify_anchors(
    tenant_id: int,
    tip_at_event: dict[int, str],
    trusted_key_resolver,
) -> list[ChainBreak]:
    """Validate every :class:`AuditChainAnchor` for ``tenant_id``.

    ``tip_at_event`` maps each event id walked by ``verify_chain`` to
    the recomputed chain tip after that event.
    """
    import base64

    from cryptography.exceptions import InvalidSignature

    from app.models.audit_chain_anchor import AuditChainAnchor
    from app.services.signing_receipts import canonical_bytes, public_key_id

    breaks: list[ChainBreak] = []
    anchors = (
        AuditChainAnchor.query.filter_by(organization_id=tenant_id)
        .order_by(AuditChainAnchor.id.asc())
        .all()
    )
    for anchor in anchors:
        try:
            key = trusted_key_resolver(anchor.key_id)
        except Exception as exc:
            breaks.append(
                ChainBreak(
                    at_id=anchor.id,
                    expected=anchor.key_id,
                    found="",
                    reason=f"anchor_key_untrusted: {exc}",
                )
            )
            continue
        if anchor.algorithm != "Ed25519":
            breaks.append(
                ChainBreak(
                    at_id=anchor.id,
                    expected="Ed25519",
                    found=anchor.algorithm,
                    reason="anchor_algorithm_unsupported",
                )
            )
            continue
        if anchor.key_id != public_key_id(key):
            breaks.append(
                ChainBreak(
                    at_id=anchor.id,
                    expected=public_key_id(key),
                    found=anchor.key_id,
                    reason="anchor_key_fingerprint_mismatch",
                )
            )
            continue
        try:
            sig = base64.b64decode(anchor.signature, validate=True)
            key.verify(sig, canonical_bytes(anchor.payload or {}))
        except (ValueError, TypeError, InvalidSignature) as exc:
            breaks.append(
                ChainBreak(
                    at_id=anchor.id,
                    expected="valid-signature",
                    found=type(exc).__name__,
                    reason="anchor_signature_invalid",
                )
            )
            continue
        payload_tip = (anchor.payload or {}).get("chain_tip_hash")
        if payload_tip != anchor.chain_tip_hash:
            breaks.append(
                ChainBreak(
                    at_id=anchor.id,
                    expected=payload_tip or "",
                    found=anchor.chain_tip_hash or "",
                    reason="anchor_payload_tip_differs_from_column",
                )
            )
            continue
        expected_tip = (
            GENESIS
            if anchor.anchor_event_id is None
            else tip_at_event.get(anchor.anchor_event_id)
        )
        if expected_tip is None:
            breaks.append(
                ChainBreak(
                    at_id=anchor.id,
                    expected=f"event:{anchor.anchor_event_id}",
                    found="missing",
                    reason="anchor_target_event_missing",
                )
            )
            continue
        if expected_tip != anchor.chain_tip_hash:
            breaks.append(
                ChainBreak(
                    at_id=anchor.id,
                    expected=expected_tip,
                    found=anchor.chain_tip_hash,
                    reason="anchor_chain_tip_mismatch",
                )
            )
    return breaks
