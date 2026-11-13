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

from app.services.platform_pdf_seal import MAX_SOURCE_BYTES, PdfFinalizationError

PLATE_WIDTH = 204
PLATE_HEIGHT = 78
MARGIN = 18


def render_stamped_source(source_bytes, *, stamp_code, stamp_name,
                          attestation_id, page_number, x_pt, y_pt):
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
                or x_pt + PLATE_WIDTH + MARGIN > width
                or y_pt + PLATE_HEIGHT + MARGIN > height):
            raise PdfFinalizationError("Stamp impression lies outside allowed page margins")
        overlay_io = BytesIO()
        c = canvas.Canvas(overlay_io, pagesize=(width, height), pageCompression=0)
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(0.8)
        c.rect(x_pt, y_pt, PLATE_WIDTH, PLATE_HEIGHT, fill=0, stroke=1)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x_pt + 10, y_pt + 56, "ORGANIZATIONAL STAMP")
        c.setFont("Helvetica", 8)
        c.drawString(x_pt + 10, y_pt + 44, "Code: " + stamp_code)
        for i, label_line in enumerate(lines):
            c.drawString(x_pt + 10, y_pt + 32 - 11 * i, label_line)
        c.setFont("Helvetica", 7)
        c.drawString(x_pt + 10, y_pt + 8, "TrustSeal attestation ID: " + str(attestation_id))
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
