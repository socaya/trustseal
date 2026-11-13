"""Render controlled textual stamp on unsigned frozen source before PDF signing.

Never overlays a pre-signed PDF: that would invalidate an existing CMS
signature. Fixed, non-decorative imprint contains a verifiable issuance ID.
"""
from io import BytesIO
import re

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.utils import ImageReader
from app.services.stamp_designs import validate_layout, INKS, SIZES

from app.services.platform_pdf_seal import MAX_SOURCE_BYTES, PdfFinalizationError

PLATE_WIDTH = 204
PLATE_HEIGHT = 78
MARGIN = 18


def _draw_plate(c, *, x_pt, y_pt, stamp_code, stamp_name, reference,
                layout=None, logo_png=None):
    layout = validate_layout(layout) if layout is not None else {
        "size": "standard", "ink": "black", "border": "rectangle",
    }
    width, height = SIZES[layout["size"]]
    ink = INKS[layout["ink"]]
    c.setStrokeColorRGB(*ink)
    c.setFillColorRGB(*ink)
    c.setLineWidth(0.8)
    if layout["border"] == "rectangle":
        c.rect(x_pt, y_pt, width, height, fill=0, stroke=1)
    content_left = x_pt + 10
    if logo_png:
        c.drawImage(
            ImageReader(BytesIO(logo_png)), content_left, y_pt + height - 48,
            width=36, height=36, preserveAspectRatio=True, anchor="c",
            mask="auto",
        )
        content_left += 44
    label_width = width - (content_left - x_pt) - 9
    lines = simpleSplit(stamp_name, "Helvetica", 8, label_width)
    if (not lines or len(lines) > 2
            or any(stringWidth(line, "Helvetica", 8) > label_width for line in lines)
            or stringWidth("Code: " + stamp_code, "Helvetica", 8) > label_width):
        raise PdfFinalizationError("Stamp label does not fit approved artwork")
    c.setFont("Helvetica-Bold", 9 if logo_png else 10)
    c.drawString(content_left, y_pt + height - 21, "ORGANIZATIONAL STAMP")
    c.setFont("Helvetica", 8)
    c.drawString(content_left, y_pt + height - 34, "Code: " + stamp_code)
    for i, line in enumerate(lines):
        c.drawString(content_left, y_pt + height - 47 - 11 * i, line)
    c.setFont("Helvetica", 7)
    c.drawString(x_pt + 10, y_pt + 8, reference)


def preview_stamp_pdf(stamp_code, stamp_name, version, layout, logo_png):
    """Render a draft specimen, not an issuable PDF or approved stamp."""
    layout = validate_layout(layout)
    width, height = SIZES[layout["size"]]
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=(width + 48, height + 68))
    _draw_plate(
        c, x_pt=24, y_pt=34, stamp_code=stamp_code,
        stamp_name=stamp_name, reference="PREVIEW - NOT ISSUED",
        layout=layout, logo_png=logo_png,
    )
    c.setFont("Helvetica", 7)
    c.drawString(24, 17, "Design version %s - SAMPLE ONLY" % version)
    c.showPage()
    c.save()
    return output.getvalue()


def render_stamped_source(source_bytes, *, stamp_code, stamp_name,
                          attestation_id, page_number, x_pt, y_pt,
                          layout=None, logo_png=None):
    if (not isinstance(source_bytes, bytes)
            or not 0 < len(source_bytes) <= MAX_SOURCE_BYTES
            or not source_bytes.startswith(b"%PDF-")):
        raise PdfFinalizationError("Unsigned PDF source is invalid")
    if (not isinstance(stamp_code, str) or not 3 <= len(stamp_code) <= 32
            or not stamp_code.isascii()
            or not isinstance(stamp_name, str) or not 3 <= len(stamp_name) <= 120
            or type(attestation_id) is not int or attestation_id <= 0
            or type(page_number) is not int or page_number < 1
            or type(x_pt) is not int or type(y_pt) is not int):
        raise PdfFinalizationError("Invalid stamp rendering parameters")
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{2,31}", stamp_code):
        raise PdfFinalizationError("Stamp code is not an approved identifier")
    if not stamp_name.strip() or any(ord(char) < 32 for char in stamp_name):
        raise PdfFinalizationError("Control characters forbidden in stamp label")
    try:
        stamp_name.encode("cp1252")
    except UnicodeEncodeError:
        raise PdfFinalizationError("Stamp label requires an approved printable font profile") from None
    layout = validate_layout(layout) if layout is not None else {"size": "standard", "ink": "black", "border": "rectangle"}
    plate_width, plate_height = SIZES[layout["size"]]
    lines = simpleSplit(stamp_name, "Helvetica", 8, PLATE_WIDTH - 20)
    if (len(lines) > 2
            or any(stringWidth(line, "Helvetica", 8) > PLATE_WIDTH - 20 for line in lines)
            or stringWidth("Code: " + stamp_code, "Helvetica", 8) > PLATE_WIDTH - 20
            or stringWidth("TrustSeal attestation ID: " + str(attestation_id),
                           "Helvetica", 7) > PLATE_WIDTH - 20):
        raise PdfFinalizationError("Stamp identity will not fit the approved plate")

    try:
        reader = PdfReader(BytesIO(source_bytes), strict=True)
        if reader.is_encrypted or not reader.pages or page_number > len(reader.pages):
            raise PdfFinalizationError("PDF encrypted or selected page unavailable")
        if reader.trailer["/Root"].get("/AcroForm") is not None:
            raise PdfFinalizationError("Interactive PDF forms not supported for stamp imprint")
        target = reader.pages[page_number - 1]
        if (int(target.get("/Rotate", 0)) != 0
                or int(target.mediabox.left) != 0 or int(target.mediabox.bottom) != 0):
            raise PdfFinalizationError("Nonstandard page origin or rotation")
        if any(page.get("/Annots") is not None for page in reader.pages):
            raise PdfFinalizationError("Annotated source cannot be safely flattened")
        width, height = float(target.mediabox.width), float(target.mediabox.height)
        if (x_pt < MARGIN or y_pt < MARGIN
                or x_pt + plate_width + MARGIN > width
                or y_pt + plate_height + MARGIN > height):
            raise PdfFinalizationError("Stamp impression lies outside allowed page margins")
        overlay_io = BytesIO()
        c = canvas.Canvas(overlay_io, pagesize=(width, height), pageCompression=0)
        _draw_plate(
            c, x_pt=x_pt, y_pt=y_pt, stamp_code=stamp_code,
            stamp_name=stamp_name,
            reference="TrustSeal attestation ID: " + str(attestation_id),
            layout=layout, logo_png=logo_png,
        )
        c.showPage()
        c.save()
        overlay = PdfReader(overlay_io)
        writer = PdfWriter()
        # Merge on an owned writer page, not a reader page that might be
        # referenced elsewhere. This also avoids deprecated pypdf behavior.
        for page in reader.pages:
            writer.add_page(page)
        writer.pages[page_number - 1].merge_page(overlay.pages[0])
        result = BytesIO()
        writer.write(result)
        raw = result.getvalue()
        if len(raw) > MAX_SOURCE_BYTES:
            raise PdfFinalizationError("Stamped source exceeds signing size limit")
        return raw
    except PdfFinalizationError:
        raise
    except Exception as exc:
        raise PdfFinalizationError("Stamp PDF rendering failed") from exc
