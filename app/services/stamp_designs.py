"""Strict stamp design allowlist, safe PNG normalization and stable evidence.

No SVG, embedded scripts, external URLs, arbitrary fonts or PDF payloads.
"""
import base64
import hashlib
import io
import json

from PIL import Image, ImageOps, UnidentifiedImageError

INKS = {"black": (0, 0, 0), "blue": (0.05, 0.19, 0.52)}
SIZES = {"standard": (204, 78), "wide": (240, 90)}
MAX_LOGO_BYTES = 80 * 1024


def validate_layout(layout):
    if not isinstance(layout, dict) or set(layout) != {"size", "ink", "border"}:
        raise ValueError("Unexpected stamp design configuration")
    if (layout["size"] not in SIZES or layout["ink"] not in INKS
            or layout["border"] not in ("rectangle", "none")):
        raise ValueError("Unsupported stamp design option")
    return dict(layout)


def normalize_png(logo_b64):
    if logo_b64 is None:
        return None, None
    if not isinstance(logo_b64, str) or len(logo_b64) > 150000:
        raise ValueError("Logo is too large")
    try:
        decoded = base64.b64decode(logo_b64, validate=True)
        if not decoded.startswith(b"\x89PNG\r\n\x1a\n") or len(decoded) > MAX_LOGO_BYTES:
            raise ValueError("Only compact PNG artwork is allowed")
        with Image.open(io.BytesIO(decoded)) as raw:
            if raw.format != "PNG" or raw.width > 512 or raw.height > 512:
                raise ValueError("Logo dimensions exceed limits")
            if raw.width < 16 or raw.height < 16:
                raise ValueError("Logo is too small")
            if raw.width * raw.height > 262144:
                raise ValueError("Logo pixel budget exceeded")
            image = ImageOps.exif_transpose(raw).convert("RGBA")
            image.thumbnail((144, 144))
            result = io.BytesIO()
            image.save(result, format="PNG", optimize=True)
        normalized = result.getvalue()
        if len(normalized) > MAX_LOGO_BYTES:
            raise ValueError("Normalized logo exceeds size limit")
        return base64.b64encode(normalized).decode("ascii"), hashlib.sha256(normalized).hexdigest()
    except (UnidentifiedImageError, OSError, ValueError, TypeError) as exc:
        raise ValueError("Invalid or unsafe logo PNG") from exc


def design_digest(layout, logo_sha256):
    validate_layout(layout)
    if logo_sha256 is not None and (
        not isinstance(logo_sha256, str)
        or len(logo_sha256) != 64
        or any(ch not in "0123456789abcdef" for ch in logo_sha256)
    ):
        raise ValueError("Invalid logo digest")
    canonical = json.dumps(
        {"schema": "trustseal.stamp-design.v1",
         "layout": layout, "logo_sha256": logo_sha256},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def checked_design(design):
    layout = validate_layout(design.layout)
    normalized, digest = normalize_png(design.logo_png_b64)
    if (digest != design.logo_sha256
            or normalized != design.logo_png_b64
            or design_digest(layout, digest) != design.design_sha256):
        raise ValueError("Stamp design integrity mismatch")
    return layout, base64.b64decode(normalized) if normalized else None
