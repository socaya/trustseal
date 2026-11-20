"""Signed, verifiable stamp-insertion receipts.

Every time a tenant stamp is dropped into a TSD, the server mints a
receipt row (``TSDStampInsertion``) with an HMAC-SHA256 signature
derived from the tenant's DEK + a stamp-scoped label. The inserted
SVG wrapper only carries the receipt id + nonce — never the signature
— so callers must round-trip through
``verify_stamp_insertion`` to prove authenticity.

Why not sign client-side? The browser has no secret. Any client-side
"signature" is a decoration, not a security control. By keeping the
HMAC key tenant-scoped and server-only, a verifier can prove the
receipt was issued by this tenant's TrustSeal instance, by a real
authenticated user, at a real time, against a specific stamp design.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime

from app.extensions import db
from app.models.tsd_stamp import TSDStamp
from app.models.tsd_stamp_insertion import TSDStampInsertion
from app.services.tsd_format import tenant_signing_key


_HMAC_LABEL = "tsd.stamp.receipt.v1"


def _canonical_bytes(**parts: str | int) -> bytes:
    """Deterministic key=value|key=value... canonicalisation."""
    return "|".join(f"{k}={parts[k]}" for k in sorted(parts)).encode("utf-8")


def issue_receipt(
    *,
    organization_id: int,
    stamp: TSDStamp,
    placed_by_id: int,
    document_id: int | None,
    context_label: str | None,
    context_svg: str,
) -> TSDStampInsertion:
    """Mint and persist a new signed receipt for a stamp impression.

    ``context_svg`` is the exact SVG about to be inserted into the
    document — it gets hashed so that any later tampering with the
    inserted mark (editing text, swapping colours) can be detected on
    verify by re-hashing the mark from the document.
    """
    nonce = secrets.token_hex(16)
    context_hash = hashlib.sha256(context_svg.encode("utf-8")).hexdigest()
    placed_at = datetime.utcnow()

    key = tenant_signing_key(organization_id, label=_HMAC_LABEL)
    payload = _canonical_bytes(
        org=organization_id,
        stamp=stamp.id,
        placed_by=placed_by_id,
        placed_at=placed_at.isoformat(timespec="seconds"),
        document=document_id or 0,
        nonce=nonce,
        ctx=context_hash,
    )
    sig = hmac.new(key, payload, hashlib.sha256).hexdigest()

    row = TSDStampInsertion(
        organization_id=organization_id,
        stamp_id=stamp.id,
        document_id=document_id,
        placed_by_id=placed_by_id,
        placed_at=placed_at,
        context_label=(context_label or "")[:200] or None,
        context_hash=context_hash,
        nonce=nonce,
        hmac_hex=sig,
        key_version=1,
    )
    db.session.add(row)
    db.session.flush()
    return row


def verify_receipt(
    *,
    organization_id: int,
    receipt_id: int,
    nonce: str,
    context_svg: str | None = None,
) -> dict:
    """Validate a receipt and (optionally) check the SVG hasn't been edited.

    Returns a result dict with:

    * ``valid``            — bool
    * ``reason``           — human-readable failure reason (if invalid)
    * ``stamp_id``, ``stamp_name``, ``stamp_kind``
    * ``placed_at``, ``placed_by_id``
    * ``revoked``          — bool
    * ``context_intact``   — bool when ``context_svg`` was supplied
    """
    row = db.session.get(TSDStampInsertion, int(receipt_id))
    if row is None or row.organization_id != organization_id:
        return {"valid": False, "reason": "receipt_not_found"}
    if not hmac.compare_digest(row.nonce, (nonce or "").strip()):
        return {"valid": False, "reason": "nonce_mismatch"}

    stamp = db.session.get(TSDStamp, row.stamp_id)
    if stamp is None or stamp.organization_id != organization_id:
        return {"valid": False, "reason": "stamp_not_found"}

    key = tenant_signing_key(organization_id, label=_HMAC_LABEL)
    payload = _canonical_bytes(
        org=row.organization_id,
        stamp=row.stamp_id,
        placed_by=row.placed_by_id,
        placed_at=row.placed_at.isoformat(timespec="seconds"),
        document=row.document_id or 0,
        nonce=row.nonce,
        ctx=row.context_hash,
    )
    expected = hmac.new(key, payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, row.hmac_hex):
        return {"valid": False, "reason": "signature_mismatch"}

    out = {
        "valid": True,
        "receipt_id": row.id,
        "stamp_id": row.stamp_id,
        "stamp_name": stamp.name,
        "stamp_kind": stamp.kind,
        "placed_at": row.placed_at.isoformat(),
        "placed_by_id": row.placed_by_id,
        "document_id": row.document_id,
        "context_label": row.context_label,
        "revoked": row.revoked_at is not None,
        "revoked_reason": row.revoked_reason,
    }

    if context_svg is not None:
        h = hashlib.sha256(context_svg.encode("utf-8")).hexdigest()
        out["context_intact"] = hmac.compare_digest(h, row.context_hash)

    return out


def canonicalize_inserted_svg(svg: str) -> str:
    """Strip ``data-stamp-receipt-*`` attributes and covert forensic layer before hashing.

    When the editor wraps the server SVG with a receipt id + nonce and/or
    embeds the TSD covert forensic `<g data-tsd-f="1">` layer, the hashed
    form must exclude those layers so the visible artwork hash stays
    deterministic and any post-issuance edit to the stamp artwork is
    immediately detected.
    """
    import re as _re
    from app.services.tsd_stamp_forensics import strip_forensic_svg_layer

    cleaned = strip_forensic_svg_layer(svg or "")
    return _re.sub(
        r'\sdata-stamp-(?:receipt-id|receipt-nonce|placed-at|placed-by)="[^"]*"',
        '',
        cleaned,
    ).strip()
