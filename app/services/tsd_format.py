"""TRUSTSEAL proprietary document (.tsd) container + crypto.

Container specification, version 1
----------------------------------

A .tsd file is a binary container composed of:

* ``Magic``   — 4 bytes ``b"TSD\\x01"``. The format version is encoded in
                the fourth byte so parsers can refuse unknown versions
                without touching the header.
* ``HdrLen``  — 4 bytes big-endian uint32. Length of the JSON header.
* ``Header``  — UTF-8 JSON bytes. See :func:`_canonical_header`.
* ``BodyLen`` — 4 bytes big-endian uint32. Length of the ciphertext body.
* ``Body``    — Fernet ciphertext bytes. The plaintext inside Fernet is
                the JSON content envelope (see :func:`pack_content`).

The header is cleartext on purpose — it's what TrustSeal needs to route
the file back to the right tenant and reject tampered copies. Nothing
sensitive goes in the header; the document body and metadata the editor
produces are inside the encrypted body.

Encryption
----------

Each tenant has a Fernet key derived deterministically from
``SECRET_KEY`` plus the organization id — one secret in ops, per-tenant
isolation at use. Fernet provides AES-128-CBC + HMAC-SHA256 with a
bundled IV and auth tag, so tampering with the ciphertext fails the
MAC check before any plaintext leaves the service.

Rotation moves through the same dual-key pattern as :mod:`app.services.mfa`:
set ``TSD_PREVIOUS_SECRET_KEYS`` in app config, rotate ``SECRET_KEY``,
then run the ``flask tsd rewrap`` command to re-encrypt stored rows
under the new key.
"""
from __future__ import annotations

import base64
import hashlib
import json
import struct
from datetime import datetime, timezone
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


MAGIC = b"TSD\x01"
HEADER_MAX = 64 * 1024  # 64 KiB
BODY_MAX = 32 * 1024 * 1024  # 32 MiB — enough for very large hand-authored drafts
CONTENT_MIME = "application/vnd.trustseal.doc+json"


class TSDError(RuntimeError):
    """Domain-level TSD failure (tampered / unreadable / version mismatch)."""


# ============================================================ key derivation


def _fernet_key(app_secret: str, organization_id: int) -> bytes:
    """Derive the per-tenant Fernet key.

    Hashes ``"tsd:" + SECRET_KEY + ":" + org_id`` so neither the app
    secret nor the tenant id can be recovered from the key alone. The
    SHA-256 digest produces a 32-byte key regardless of input length;
    operators are still responsible for choosing a high-entropy
    ``SECRET_KEY`` — this derivation adds domain separation, not
    entropy.
    """
    if not isinstance(app_secret, str) or not app_secret:
        raise TSDError("SECRET_KEY is required")
    if not isinstance(organization_id, int) or organization_id <= 0:
        raise TSDError("organization_id must be a positive integer")
    material = f"tsd:{app_secret}:{organization_id}".encode("utf-8")
    raw = hashlib.sha256(material).digest()
    return base64.urlsafe_b64encode(raw)


def _tenant_fernets(organization_id: int) -> list[Fernet]:
    """Return the active Fernet first, then any rotation fallbacks."""
    primary = current_app.config.get("SECRET_KEY")
    if not primary:
        raise TSDError("SECRET_KEY is not configured")
    keys = [_fernet_key(primary, organization_id)]
    for prev in current_app.config.get("TSD_PREVIOUS_SECRET_KEYS", []) or []:
        if isinstance(prev, str) and prev:
            keys.append(_fernet_key(prev, organization_id))
    return [Fernet(k) for k in keys]


# ============================================================ content envelope


def pack_content(
    *,
    html: str,
    description: str | None = None,
    tags: list[str] | None = None,
    extras: dict[str, Any] | None = None,
) -> bytes:
    """Serialize the editor's content into the canonical JSON envelope.

    This is what Fernet wraps. Keeping it JSON lets us version the
    schema without breaking older stored rows.
    """
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
    """Encrypt the content envelope with the tenant's active Fernet key."""
    if len(plaintext) > BODY_MAX:
        raise TSDError(f"content exceeds TSD body limit ({BODY_MAX} bytes)")
    fernets = _tenant_fernets(organization_id)
    return fernets[0].encrypt(plaintext)


def decrypt_content_envelope(ciphertext: bytes, *, organization_id: int) -> dict[str, Any]:
    """Decrypt the stored ciphertext, trying rotation keys as fallbacks."""
    last_exc: Exception | None = None
    for fernet in _tenant_fernets(organization_id):
        try:
            return unpack_content(fernet.decrypt(ciphertext))
        except InvalidToken as exc:
            last_exc = exc
            continue
    raise TSDError("ciphertext failed authentication under all tenant keys") from last_exc


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
        "encryption": "fernet-tenant-scoped",
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
    """Produce the downloadable .tsd bytes."""
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
    """Inverse of :func:`serialize_container`. Returns (header, ciphertext).

    Rejects unknown magic / version and over-long sections before
    allocating memory for the body.
    """
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
