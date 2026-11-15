"""Persist optional drawn signature appearances.

The appearance PNG is uploaded alongside the review decision form.
This service validates the payload, hashes it, writes it to private
storage under a subdirectory separate from document blobs so a bulk
tenant export never mixes signer appearances with content, and
persists the :class:`SignerAppearance` metadata row.

Contract:

* Accepts a ``data:image/png;base64,...`` URL or raw PNG bytes.
* Caps the payload at 256 KiB (the model check constraint matches).
* Requires a valid PNG magic prefix — the PDF seal path later embeds
  the image, and the client may be hostile.
* Stores the file under ``{PRIVATE_DOCUMENT_ROOT}/signer-appearances/``
  with a 64-hex filename. The directory is created on demand with
  mode 0700.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import secrets
import stat
from pathlib import Path
from typing import Any

from app.extensions import db
from app.models.signer_appearance import SignerAppearance
from app.models.signer_decision import SignerDecision
from app.models.signing_envelope import EnvelopeParticipant, SigningEnvelope

MAX_APPEARANCE_BYTES = 256 * 1024
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_DATA_URL_RE = re.compile(r"^data:image/png;base64,([A-Za-z0-9+/=\s]+)$")


class AppearanceError(RuntimeError):
    """The appearance payload is malformed or oversized."""


def decode(payload: str | bytes) -> bytes:
    """Return raw PNG bytes from a data-URL or raw-bytes input."""
    if isinstance(payload, (bytes, bytearray)):
        data = bytes(payload)
    elif isinstance(payload, str):
        match = _DATA_URL_RE.match(payload.strip())
        if not match:
            raise AppearanceError("appearance_must_be_png_data_url")
        try:
            data = base64.b64decode(match.group(1), validate=True)
        except (ValueError, TypeError) as exc:
            raise AppearanceError("appearance_base64_invalid") from exc
    else:
        raise AppearanceError("appearance_must_be_png_data_url")
    if not data:
        raise AppearanceError("appearance_empty")
    if len(data) > MAX_APPEARANCE_BYTES:
        raise AppearanceError("appearance_too_large")
    if not data.startswith(PNG_MAGIC):
        raise AppearanceError("appearance_not_png")
    return data


def _appearance_root(config: Any) -> Path:
    base = config.get("PRIVATE_DOCUMENT_ROOT")
    if not base:
        raise AppearanceError("private_storage_not_configured")
    root = Path(base).resolve() / "signer-appearances"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if stat.S_IMODE(root.stat().st_mode) & 0o077:
        raise AppearanceError("appearance_root_permissions")
    return root


def store(
    *,
    decision: SignerDecision,
    envelope: SigningEnvelope,
    participant: EnvelopeParticipant,
    payload: str | bytes,
    config: Any,
) -> SignerAppearance:
    """Validate ``payload``, persist it, and return the metadata row.

    Raises :class:`AppearanceError` for every validation failure so
    the view layer can map to a user-visible message. Storage writes
    use exclusive-create so a hash collision (astronomically unlikely
    for SHA-256) is surfaced rather than silently overwriting.
    """
    if decision.envelope_id != envelope.id:
        raise AppearanceError("decision_envelope_mismatch")
    if decision.participant_id != participant.id:
        raise AppearanceError("decision_participant_mismatch")
    data = decode(payload)
    sha256 = hashlib.sha256(data).hexdigest()
    object_name = sha256 + ".png"
    root = _appearance_root(config)
    target = root / object_name
    try:
        fd = os.open(
            str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400
        )
    except FileExistsError:
        raise AppearanceError("appearance_hash_collision")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    row = SignerAppearance(
        decision_id=decision.id,
        envelope_id=envelope.id,
        participant_id=participant.id,
        user_id=participant.user_id,
        sha256=sha256,
        size_bytes=len(data),
        object_key=f"signer-appearances/{object_name}",
    )
    db.session.add(row)
    db.session.flush()
    return row


def cleanup(object_key: str, config: Any) -> None:
    """Delete an appearance file by object key; used on rollback paths."""
    if (
        not isinstance(object_key, str)
        or not object_key.startswith("signer-appearances/")
        or ".." in object_key
    ):
        return
    base = config.get("PRIVATE_DOCUMENT_ROOT")
    if not base:
        return
    path = Path(base).resolve() / object_key
    try:
        path.unlink()
    except FileNotFoundError:
        pass
