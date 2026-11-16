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
JPEG_MAGIC = b"\xff\xd8\xff"
_DATA_URL_RE = re.compile(r"^data:image/png;base64,([A-Za-z0-9+/=\s]+)$")

TYPED_PNG_WIDTH = 480
TYPED_PNG_HEIGHT = 120
TYPED_FONT_SIZE = 56
MAX_TYPED_NAME_LEN = 80


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
    appearance_kind: str = "drawn",
    source_label: str | None = None,
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
    if appearance_kind not in {"drawn", "typed", "uploaded"}:
        raise AppearanceError("appearance_kind_invalid")
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
        appearance_kind=appearance_kind,
        source_label=source_label,
    )
    db.session.add(row)
    db.session.flush()
    return row


# ---------------------------------------------------------------- I2 typed


def render_typed(name: str, *, config: Any) -> bytes:
    """Render ``name`` as a handwritten-style PNG for a typed signature.

    The rendering is deliberately simple: a single centered line in a
    handwriting-style font on a transparent background. The orchestrator
    treats the resulting PNG identically to a drawn appearance when
    stamping it into the sealed PDF.

    Gated by ``TYPED_SIGNATURE_RENDERING_ENABLED`` so operators can
    disable the typed path in jurisdictions that require a manuscript
    signature appearance.
    """
    if not bool(config.get("TYPED_SIGNATURE_RENDERING_ENABLED")):
        raise AppearanceError("typed_rendering_disabled")
    if not isinstance(name, str):
        raise AppearanceError("typed_name_type_invalid")
    cleaned = name.strip()
    if not 1 <= len(cleaned) <= MAX_TYPED_NAME_LEN:
        raise AppearanceError("typed_name_invalid")
    # Reject control characters so we never render newlines or backspaces.
    if any(ord(ch) < 32 for ch in cleaned):
        raise AppearanceError("typed_name_contains_control_chars")
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGBA", (TYPED_PNG_WIDTH, TYPED_PNG_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Try a cursive-leaning TrueType; fall back to the Pillow default
    # bitmap font if no system font is available.
    font = None
    for candidate in (
        "/System/Library/Fonts/Supplemental/Snell Roundhand.ttc",
        "/System/Library/Fonts/Supplemental/Apple Chancery.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
    ):
        try:
            font = ImageFont.truetype(candidate, TYPED_FONT_SIZE)
            break
        except (OSError, ValueError):
            continue
    if font is None:
        font = ImageFont.load_default()
    # Centre the text horizontally, baseline roughly 2/3 down.
    bbox = draw.textbbox((0, 0), cleaned, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = max(0, (TYPED_PNG_WIDTH - text_w) // 2)
    y = max(0, (TYPED_PNG_HEIGHT - text_h) // 2 - 10)
    draw.text((x, y), cleaned, fill=(0, 0, 0, 255), font=font)
    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------- I3 uploaded


def normalise_uploaded(payload: bytes, *, max_bytes: int = MAX_APPEARANCE_BYTES) -> bytes:
    """Validate an uploaded PNG/JPEG and return a normalised PNG byte-string.

    JPEGs are decoded with Pillow and re-encoded to PNG so the sealed
    PDF embed path is uniform. Oversized or non-image payloads raise.
    """
    if not isinstance(payload, (bytes, bytearray)):
        raise AppearanceError("appearance_must_be_bytes")
    if not payload:
        raise AppearanceError("appearance_empty")
    if len(payload) > max_bytes:
        raise AppearanceError("appearance_too_large")
    if payload.startswith(PNG_MAGIC):
        return bytes(payload)
    if payload.startswith(JPEG_MAGIC):
        import io

        from PIL import Image

        try:
            with Image.open(io.BytesIO(payload)) as source:
                source.load()
                if source.mode != "RGBA":
                    source = source.convert("RGBA")
                buf = io.BytesIO()
                source.save(buf, format="PNG", optimize=True)
                converted = buf.getvalue()
        except (OSError, ValueError) as exc:
            raise AppearanceError("appearance_unreadable") from exc
        if len(converted) > max_bytes:
            raise AppearanceError("appearance_too_large_after_normalise")
        return converted
    raise AppearanceError("appearance_format_unsupported")


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
