"""TRUSTSEAL proprietary document (.tsd) container + crypto.

Container specification, version 1
----------------------------------

A .tsd file is a binary container composed of:

* ``Magic``   — 4 bytes ``b"TSD\\x01"``.
* ``HdrLen``  — 4 bytes big-endian uint32.
* ``Header``  — UTF-8 JSON bytes. See :func:`_canonical_header`.
* ``BodyLen`` — 4 bytes big-endian uint32.
* ``Body``    — Fernet ciphertext. The plaintext inside Fernet is the
                JSON content envelope (see :func:`pack_content`).

Key management — envelope encryption
------------------------------------

Each tenant has a random 32-byte Fernet key — the Data Encryption Key
(DEK) — generated the first time a document is written for that
tenant. The raw DEK is **never** stored. What's persisted in the
``tenant_keys`` table is the DEK wrapped (envelope-encrypted) by a
master Key Encryption Key (KEK) derived from the server's
``SECRET_KEY``.

Two independent rotation axes:

* **Master KEK rotation** — `flask tsd rewrap --master` re-wraps every
  tenant's DEK under the new master, leaving document ciphertext
  untouched.
* **Tenant DEK rotation** — `flask tsd rewrap --tenant <id>` generates
  a new random DEK and re-encrypts every document in that tenant
  under it.

A single ``SECRET_KEY`` compromise is still serious (the attacker can
unwrap every tenant's DEK from the database), but the separation is
what lets individual tenants rotate without disturbing others and sets
the shape for a future KMS-backed KEK.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import struct
from datetime import datetime, timezone
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

from app.extensions import db


MAGIC = b"TSD\x01"
HEADER_MAX = 64 * 1024  # 64 KiB
BODY_MAX = 32 * 1024 * 1024  # 32 MiB
CONTENT_MIME = "application/vnd.trustseal.doc+json"


class TSDError(RuntimeError):
    """Domain-level TSD failure (tampered / unreadable / unauthorized)."""


# ============================================================ master KEK


def _master_kek(app_secret: str | None = None) -> Fernet:
    """Derive the master Key Encryption Key used to wrap tenant DEKs."""
    secret = app_secret or current_app.config.get("SECRET_KEY")
    if not isinstance(secret, str) or not secret:
        raise TSDError("SECRET_KEY is required")
    raw = hashlib.sha256(("tsd-kek:" + secret).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(raw))


def _previous_master_keks() -> list[Fernet]:
    """Rotation fallbacks for the master KEK."""
    out: list[Fernet] = []
    for prev in current_app.config.get("TSD_PREVIOUS_SECRET_KEYS", []) or []:
        if isinstance(prev, str) and prev:
            try:
                out.append(_master_kek(prev))
            except TSDError:
                pass
    return out


# ============================================================ tenant DEK


def _generate_dek() -> bytes:
    """Fresh random 32-byte Fernet key, url-safe-base64 encoded."""
    return base64.urlsafe_b64encode(os.urandom(32))


def _unwrap_dek(wrapped: bytes) -> bytes:
    """Unwrap a stored DEK using the active KEK, falling back to previous."""
    last_exc: Exception | None = None
    for kek in (_master_kek(), *_previous_master_keks()):
        try:
            return kek.decrypt(wrapped)
        except InvalidToken as exc:
            last_exc = exc
    raise TSDError(
        "could not unwrap tenant key — SECRET_KEY may have been rotated "
        "without running `flask tsd rewrap --master`"
    ) from last_exc


def _tenant_fernet(organization_id: int) -> Fernet:
    """Get-or-create the Fernet for a tenant.

    Lazy provisioning: the first document write for a tenant generates
    its DEK, wraps it under the master KEK, and commits.
    """
    from app.models.tenant_key import TenantKey  # local import avoids cycle

    if not isinstance(organization_id, int) or organization_id <= 0:
        raise TSDError("organization_id must be a positive integer")

    row = db.session.get(TenantKey, organization_id)
    if row is None:
        dek = _generate_dek()
        row = TenantKey(
            organization_id=organization_id,
            wrapped_key=_master_kek().encrypt(dek),
        )
        db.session.add(row)
        db.session.flush()  # surface IntegrityError now, not at commit
    else:
        dek = _unwrap_dek(row.wrapped_key)

    return Fernet(dek)


def ensure_tenant_key(organization_id: int) -> None:
    """Public helper for CLI/tests to pre-provision a tenant's DEK."""
    _tenant_fernet(organization_id)
    db.session.commit()


def tenant_signing_key(organization_id: int, *, label: str) -> bytes:
    """Return a 32-byte HMAC key derived from the tenant DEK + a label.

    Used for signing non-document artefacts (stamp receipts, share
    tokens) without exposing the raw DEK and with domain separation
    per use case. Different ``label`` values produce different keys
    even for the same tenant.
    """
    from app.models.tenant_key import TenantKey

    row = db.session.get(TenantKey, organization_id)
    if row is None:
        _tenant_fernet(organization_id)
        row = db.session.get(TenantKey, organization_id)
    dek = _unwrap_dek(row.wrapped_key)
    return hashlib.sha256(b"trustseal/v1/" + label.encode("utf-8")
                          + b"\x00" + dek).digest()


# ============================================================ content envelope


def pack_content(
    *,
    html: str,
    description: str | None = None,
    tags: list[str] | None = None,
    extras: dict[str, Any] | None = None,
) -> bytes:
    envelope: dict[str, Any] = {
        "schema": "trustseal.doc.v1",
        "html": html or "",
        "description": description or "",
        "tags": tags or [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if extras:
        envelope["extras"] = extras
    return json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def unpack_content(blob: bytes) -> dict[str, Any]:
    try:
        data = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TSDError("content envelope is not valid JSON") from exc
    if not isinstance(data, dict) or data.get("schema") != "trustseal.doc.v1":
        raise TSDError("content envelope is not a trustseal.doc.v1 envelope")
    return data


# ============================================================ encrypt / decrypt


def encrypt_content_envelope(plaintext: bytes, *, organization_id: int) -> bytes:
    if len(plaintext) > BODY_MAX:
        raise TSDError(f"content exceeds TSD body limit ({BODY_MAX} bytes)")
    return _tenant_fernet(organization_id).encrypt(plaintext)


def decrypt_content_envelope(ciphertext: bytes, *, organization_id: int) -> dict[str, Any]:
    try:
        plaintext = _tenant_fernet(organization_id).decrypt(ciphertext)
    except InvalidToken as exc:
        raise TSDError("ciphertext failed authentication under tenant DEK") from exc
    return unpack_content(plaintext)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ============================================================ container I/O


def _canonical_header(
    *,
    organization_id: int,
    document_id: int,
    document_version: int,
    title: str,
    created_by_id: int,
    created_at: datetime,
    ciphertext_sha256: str,
    export_policy: str,
) -> bytes:
    header = {
        "format": "tsd",
        "version": 1,
        "mime": CONTENT_MIME,
        "encryption": "fernet-tenant-dek-wrapped",
        "tenant_id": int(organization_id),
        "document_id": int(document_id),
        "document_version": int(document_version),
        "title": title,
        "created_by": int(created_by_id),
        "created_at": created_at.astimezone(timezone.utc).isoformat()
        if created_at.tzinfo else
        created_at.replace(tzinfo=timezone.utc).isoformat(),
        "ciphertext_sha256": ciphertext_sha256,
        "export_policy": export_policy,
    }
    return json.dumps(header, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def serialize_container(
    *,
    organization_id: int,
    document_id: int,
    document_version: int,
    title: str,
    created_by_id: int,
    created_at: datetime,
    ciphertext: bytes,
    export_policy: str,
) -> bytes:
    ciphertext_sha256 = sha256_hex(ciphertext)
    header = _canonical_header(
        organization_id=organization_id,
        document_id=document_id,
        document_version=document_version,
        title=title,
        created_by_id=created_by_id,
        created_at=created_at,
        ciphertext_sha256=ciphertext_sha256,
        export_policy=export_policy,
    )
    if len(header) > HEADER_MAX:
        raise TSDError("header exceeds TSD header limit")
    if len(ciphertext) > BODY_MAX:
        raise TSDError("ciphertext exceeds TSD body limit")
    return (
        MAGIC
        + struct.pack(">I", len(header))
        + header
        + struct.pack(">I", len(ciphertext))
        + ciphertext
    )


def parse_container(blob: bytes) -> tuple[dict[str, Any], bytes]:
    if len(blob) < 12:
        raise TSDError("tsd container too short")
    if blob[:4] != MAGIC:
        raise TSDError("tsd magic mismatch — not a TrustSeal document")
    hdr_len = struct.unpack(">I", blob[4:8])[0]
    if hdr_len > HEADER_MAX:
        raise TSDError("tsd header too large")
    header_bytes = blob[8 : 8 + hdr_len]
    if len(header_bytes) != hdr_len:
        raise TSDError("tsd header truncated")
    try:
        header = json.loads(header_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TSDError("tsd header is not valid JSON") from exc
    if header.get("format") != "tsd" or header.get("version") != 1:
        raise TSDError("unsupported tsd format/version")

    body_off = 8 + hdr_len
    if len(blob) < body_off + 4:
        raise TSDError("tsd body length missing")
    body_len = struct.unpack(">I", blob[body_off : body_off + 4])[0]
    if body_len > BODY_MAX:
        raise TSDError("tsd body too large")
    body = blob[body_off + 4 : body_off + 4 + body_len]
    if len(body) != body_len:
        raise TSDError("tsd body truncated")

    if header.get("ciphertext_sha256") != sha256_hex(body):
        raise TSDError("tsd ciphertext hash mismatch — tamper detected")

    return header, body


# ============================================================ rotation


def rewrap_master(*, previous_secret: str) -> int:
    """Re-encrypt every tenant DEK under the current master KEK.

    Call after rotating ``SECRET_KEY``. ``previous_secret`` must be the
    old value so the old wrappers can be unwrapped. Returns the number
    of tenant rows re-wrapped.
    """
    from app.models.tenant_key import TenantKey

    old_kek = _master_kek(previous_secret)
    new_kek = _master_kek()
    count = 0
    for row in TenantKey.query.all():
        dek = old_kek.decrypt(row.wrapped_key)
        row.wrapped_key = new_kek.encrypt(dek)
        row.master_key_version += 1
        row.rotated_at = datetime.utcnow()
        count += 1
    db.session.commit()
    return count


def rotate_tenant_key(organization_id: int) -> int:
    """Generate a fresh DEK for a tenant and re-encrypt all their documents.

    Returns the number of documents re-encrypted.
    """
    from app.models.tenant_key import TenantKey
    from app.models.tsd_document import TSDocument

    row = db.session.get(TenantKey, organization_id)
    if row is None:
        raise TSDError(f"tenant {organization_id} has no DEK provisioned")

    old_fernet = Fernet(_unwrap_dek(row.wrapped_key))
    new_dek = _generate_dek()
    new_fernet = Fernet(new_dek)

    count = 0
    docs = (
        TSDocument.query
        .filter_by(organization_id=organization_id)
        .all()
    )
    for d in docs:
        plaintext = old_fernet.decrypt(d.ciphertext)
        d.ciphertext = new_fernet.encrypt(plaintext)
        d.ciphertext_sha256 = sha256_hex(d.ciphertext)
        count += 1

    row.wrapped_key = _master_kek().encrypt(new_dek)
    row.tenant_key_version += 1
    row.rotated_at = datetime.utcnow()
    db.session.commit()
    return count


# ============================================================ sanitization


_ALLOWED_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "code", "div", "em", "figure",
    "figcaption", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i",
    "img", "li", "ol", "p", "pre", "span", "strong", "sub", "sup",
    "table", "tbody", "td", "th", "thead", "tr", "u", "ul",
}
_ALLOWED_ATTRS = {
    "*": [
        "style", "class", "title", "contenteditable",
        "data-tsd-marks", "data-tsd-stamp-receipt", "data-tsd-stamp-nonce",
        "data-tsd-stamp-date", "data-tsd-sig-id", "data-tsd-sig-usage",
        "data-tsd-group", "data-align",
    ],
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "width", "height", "draggable"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan", "scope"],
}
_ALLOWED_STYLES = {
    "color", "background", "background-color", "font-family", "font-size",
    "font-weight", "font-style", "text-align", "text-decoration", "line-height",
    "margin", "margin-top", "margin-bottom", "margin-left", "margin-right",
    "padding", "padding-top", "padding-bottom", "padding-left", "padding-right",
    "border", "border-left", "border-right", "border-collapse", "border-top",
    "border-bottom", "letter-spacing", "width", "min-width", "max-width",
    "height", "max-height", "display", "flex-wrap", "align-items",
    "justify-content", "gap", "vertical-align", "position", "z-index",
    "overflow", "user-select", "pointer-events", "transform",
}
_ALLOWED_PROTOCOLS = {"http", "https", "mailto", "data"}

_SAFE_SVG_TAGS = frozenset({
    "svg", "g", "defs", "path", "circle", "ellipse", "rect", "polygon",
    "polyline", "line", "text", "textPath", "tspan", "image", "clipPath",
    "mask", "filter", "linearGradient", "radialGradient", "stop",
    "feTurbulence", "feDisplacementMap", "feColorMatrix", "feComposite",
    "feGaussianBlur", "feComponentTransfer", "feFuncA", "feFuncR",
    "feFuncG", "feFuncB", "feMerge", "feMergeNode", "feMorphology",
})


def _sanitize_svg_fragment(svg_raw: str) -> str:
    """Strictly sanitize an inline SVG (stamp or vector signature) while preserving SVG camelCase."""
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(svg_raw)
    except Exception:
        return ""

    def _local(tag: str) -> str:
        return tag.split("}", 1)[1] if "}" in tag else tag

    if _local(root.tag) != "svg":
        return ""

    def _clean_el(el: ET.Element) -> ET.Element | None:
        lname = _local(el.tag)
        if lname not in _SAFE_SVG_TAGS:
            return None
        new_el = ET.Element(lname)
        new_el.text = el.text
        new_el.tail = el.tail
        for k, v in el.attrib.items():
            ak = _local(k)
            kl = ak.lower()
            if kl.startswith("on") or kl in ("xmlns:xlink",):
                continue
            if kl == "href":
                vs = (v or "").strip()
                if not (vs.startswith("#") or vs.startswith("data:image/") or vs.startswith("/static/")):
                    continue
            if "javascript:" in (v or "").lower():
                continue
            new_el.set(ak, v)
        for child in list(el):
            cleaned_child = _clean_el(child)
            if cleaned_child is not None:
                new_el.append(cleaned_child)
        return new_el

    cleaned_root = _clean_el(root)
    if cleaned_root is None:
        return ""
    cleaned_root.set("xmlns", "http://www.w3.org/2000/svg")
    return ET.tostring(cleaned_root, encoding="unicode")


def sanitize_html(raw: str, *, allow_data_images: bool = True) -> str:
    """Strip XSS vectors from ingested or editor-authored HTML while preserving
    forensically sealed SVG stamps and verified staff signatures.
    """
    if not raw:
        return ""
    import bleach
    from bleach.css_sanitizer import CSSSanitizer

    # Extract <svg>...</svg> blocks before bleach.clean so bleach never lowercases
    # or strips SVG camelCase tags/attributes (viewBox, textPath, feTurbulence, etc.).
    svg_slots: list[str] = []

    def _stash_svg(match: re.Match) -> str:
        safe_svg = _sanitize_svg_fragment(match.group(0))
        if not safe_svg:
            return ""
        idx = len(svg_slots)
        svg_slots.append(safe_svg)
        return f"__TSD_SAFE_SVG_{idx}__"

    stashed = re.sub(r"<svg\b[^>]*>.*?</svg>", _stash_svg, raw, flags=re.IGNORECASE | re.DOTALL)

    css = CSSSanitizer(allowed_css_properties=sorted(_ALLOWED_STYLES))

    protocols = set(_ALLOWED_PROTOCOLS)
    if not allow_data_images:
        protocols.discard("data")

    cleaned = bleach.clean(
        stashed,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        protocols=protocols,
        css_sanitizer=css,
        strip=True,
    )
    # Second pass: non-image data: URIs slip through the protocol
    # filter above because bleach only inspects ``href``/``src`` text.
    cleaned = re.sub(
        r'<(?!img\b)([a-zA-Z][^\s>]*)([^>]*?)(href|src)\s*=\s*"data:[^"]*"',
        r'<\1\2',
        cleaned,
        flags=re.IGNORECASE,
    )
    for idx, safe_svg in enumerate(svg_slots):
        cleaned = cleaned.replace(f"__TSD_SAFE_SVG_{idx}__", safe_svg)
    return cleaned
