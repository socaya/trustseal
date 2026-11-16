"""Isolated PNG/JPEG → PDF conversion.

Converts a single image upload to a one-page PDF that the rest of
the document pipeline can treat identically to a native PDF. The
conversion is deliberately lossless-friendly (no re-compression of
JPEGs, PNG RGBA flattened to RGB on a white background).

Constraints:

* Only PNG and JPEG are accepted. Other formats (BMP, TIFF, HEIC)
  require a separate decoder and are refused with
  ``ImageConversionError("format_unsupported")``.
* Image magic is checked explicitly — relying on the client-supplied
  ``Content-Type`` is not sufficient.
* Maximum input bytes default to 25 MiB (``IMAGE_CONVERSION_MAX_BYTES``);
  larger images are rejected before decoding so a malformed huge
  file cannot exhaust memory.
* Maximum pixel count defaults to 50 megapixels
  (``IMAGE_CONVERSION_MAX_PIXELS``) so a small compressed file
  cannot expand to a billion-pixel bitmap (a well-known decoder
  attack).

The function returns raw PDF bytes; the caller writes them to
private storage via the existing ``store_scanned_pdf`` ingestion
path so antivirus + digest + manifest invariants still apply.
"""
from __future__ import annotations

import io
from typing import Mapping

from PIL import Image, ImageFile
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


# Let Pillow raise ``DecompressionBombError`` on suspiciously large
# images rather than silently load them.
Image.MAX_IMAGE_PIXELS = 50_000_000
# Refuse to parse truncated image streams — a truncated JPEG can hide
# polyglot content past the EOI marker.
ImageFile.LOAD_TRUNCATED_IMAGES = False


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
DEFAULT_MAX_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_PIXELS = 50_000_000
DEFAULT_PAGE_MARGIN_PT = 36  # 0.5 inch margin


class ImageConversionError(RuntimeError):
    """Raised when the source image is not a supported PNG/JPEG upload."""


def _enabled(config: Mapping) -> bool:
    return bool(config.get("IMAGE_PDF_CONVERSION_ENABLED"))


def _max_bytes(config: Mapping) -> int:
    value = config.get("IMAGE_CONVERSION_MAX_BYTES")
    return int(value) if value else DEFAULT_MAX_BYTES


def _max_pixels(config: Mapping) -> int:
    value = config.get("IMAGE_CONVERSION_MAX_PIXELS")
    return int(value) if value else DEFAULT_MAX_PIXELS


def detect_format(payload: bytes) -> str:
    """Return ``"png"``, ``"jpeg"``, or raise ``ImageConversionError``."""
    if payload.startswith(PNG_MAGIC):
        return "png"
    if payload.startswith(JPEG_MAGIC):
        return "jpeg"
    raise ImageConversionError("format_unsupported")


def convert_to_pdf(payload: bytes, *, config: Mapping) -> bytes:
    """Return PDF bytes for a PNG or JPEG ``payload``.

    Caller must have already enforced authentication + tenant context.
    """
    if not _enabled(config):
        raise ImageConversionError("conversion_disabled")
    if not isinstance(payload, (bytes, bytearray)):
        raise ImageConversionError("payload_type_invalid")
    if len(payload) == 0:
        raise ImageConversionError("payload_empty")
    max_bytes = _max_bytes(config)
    if len(payload) > max_bytes:
        raise ImageConversionError(f"payload_too_large:{len(payload)}>{max_bytes}")
    detect_format(payload)
    try:
        with Image.open(io.BytesIO(payload)) as source:
            source.load()
            width, height = source.size
            if width * height > _max_pixels(config):
                raise ImageConversionError("image_too_many_pixels")
            flattened = _flatten(source)
    except Image.DecompressionBombError as exc:
        raise ImageConversionError("image_decompression_bomb") from exc
    except Image.UnidentifiedImageError as exc:
        raise ImageConversionError("image_unreadable") from exc
    except OSError as exc:
        raise ImageConversionError("image_unreadable") from exc
    return _render_single_page_pdf(flattened)


def _flatten(image: Image.Image) -> Image.Image:
    """Return an RGB-mode copy of ``image``, flattening alpha onto white."""
    if image.mode in ("RGB", "L"):
        return image.convert("RGB")
    if image.mode == "RGBA":
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[-1])
        return background
    if image.mode == "P":
        return image.convert("RGB")
    return image.convert("RGB")


def _render_single_page_pdf(image: Image.Image) -> bytes:
    """Lay out ``image`` on a letter-sized PDF page with a safe margin."""
    from reportlab.lib.pagesizes import letter

    page_width, page_height = letter
    margin = DEFAULT_PAGE_MARGIN_PT
    frame_width = page_width - 2 * margin
    frame_height = page_height - 2 * margin
    img_width, img_height = image.size
    scale = min(frame_width / img_width, frame_height / img_height)
    draw_width = img_width * scale
    draw_height = img_height * scale
    x = (page_width - draw_width) / 2
    y = (page_height - draw_height) / 2
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.drawImage(
        ImageReader(image),
        x,
        y,
        width=draw_width,
        height=draw_height,
        preserveAspectRatio=True,
        mask="auto",
    )
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
