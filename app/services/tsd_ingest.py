"""Ingest PDF / DOCX / XLSX / TXT / HTML / image uploads into TrustSeal HTML.

Image uploads embed the picture inline as a base64 data URI and, when
Tesseract is available (``pytesseract`` + ``tesseract`` binary in PATH),
also prepend the OCR'd text as paragraphs so the document is searchable
and editable.

Output HTML is what the editor renders and what the ``.tsd`` content
envelope stores. We keep it minimal (semantic tags only) so re-editing
in the browser produces clean, predictable markup.
"""
from __future__ import annotations

import base64
import io
import html as html_std
from typing import BinaryIO


class IngestError(RuntimeError):
    """Domain-level ingest failure (unsupported type, corrupt file, …)."""


SUPPORTED_SUFFIXES = (
    ".pdf", ".docx", ".xlsx", ".txt", ".html", ".htm", ".md",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif",
)
IMAGE_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif",
)
MAX_PAGES = 400       # safety ceiling for huge PDFs
MAX_BYTES = 25 * 1024 * 1024

# OCR capability is probed lazily so the service runs cleanly even when
# tesseract isn't installed on the host.
_OCR_AVAILABLE: bool | None = None


def _ocr_available() -> bool:
    global _OCR_AVAILABLE
    if _OCR_AVAILABLE is not None:
        return _OCR_AVAILABLE
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
        # Probe the binary — pytesseract shells out to ``tesseract``.
        pytesseract.get_tesseract_version()
        _OCR_AVAILABLE = True
    except Exception:
        _OCR_AVAILABLE = False
    return _OCR_AVAILABLE


def ingest(filename: str, stream: BinaryIO) -> tuple[str, dict]:
    """Return (html, metadata) for the uploaded file."""
    data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise IngestError(f"file exceeds {MAX_BYTES} byte limit")
    if not data:
        raise IngestError("empty file")

    lower = (filename or "").lower()
    if lower.endswith(".pdf"):
        return _ingest_pdf(data)
    if lower.endswith(".docx"):
        return _ingest_docx(data)
    if lower.endswith(".xlsx"):
        return _ingest_xlsx(data)
    if lower.endswith((".txt", ".md")):
        return _ingest_text(data)
    if lower.endswith((".html", ".htm")):
        return _ingest_html(data)
    if lower.endswith(IMAGE_SUFFIXES):
        return _ingest_image(data, filename)
    raise IngestError(
        f"unsupported file type: expected one of {', '.join(SUPPORTED_SUFFIXES)}"
    )


# -------------------------------------------------------------------- PDF


def _ingest_pdf(data: bytes) -> tuple[str, dict]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise IngestError(f"could not open PDF: {exc}") from exc

    pages = reader.pages
    if len(pages) > MAX_PAGES:
        raise IngestError(f"PDF has {len(pages)} pages; limit is {MAX_PAGES}")

    out: list[str] = []
    for idx, page in enumerate(pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if idx > 1:
            out.append('<hr style="margin: 24pt 0; border: 0; border-top: 1px dashed #c7ced6;">')
        out.append(f'<p style="color:#5a6676; font-size:9pt; letter-spacing:0.08em;">PAGE {idx}</p>')
        for para in text.split("\n\n"):
            para = para.strip()
            if not para:
                continue
            out.append(f"<p>{html_std.escape(para).replace(chr(10), '<br>')}</p>")

    return "\n".join(out), {
        "source_type": "pdf",
        "page_count": len(pages),
    }


# -------------------------------------------------------------------- DOCX


def _ingest_docx(data: bytes) -> tuple[str, dict]:
    import docx  # python-docx

    try:
        doc = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise IngestError(f"could not open DOCX: {exc}") from exc

    out: list[str] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        style = (para.style.name or "").lower() if para.style else ""
        if not text:
            continue
        escaped = html_std.escape(text)
        if "heading 1" in style or style == "title":
            out.append(f"<h1>{escaped}</h1>")
        elif "heading 2" in style:
            out.append(f"<h2>{escaped}</h2>")
        elif "heading 3" in style:
            out.append(f"<h3>{escaped}</h3>")
        elif "heading" in style:
            out.append(f"<h4>{escaped}</h4>")
        elif "list" in style or "bullet" in style:
            out.append(f"<ul><li>{escaped}</li></ul>")
        else:
            out.append(f"<p>{escaped}</p>")

    # Include tables as simple HTML tables.
    for table in doc.tables:
        rows_html = []
        for row in table.rows:
            cells = "".join(f"<td>{html_std.escape(c.text.strip())}</td>" for c in row.cells)
            rows_html.append(f"<tr>{cells}</tr>")
        if rows_html:
            out.append(
                '<table style="border-collapse: collapse; margin: 12pt 0;">'
                + "".join(rows_html)
                + "</table>"
            )

    return "\n".join(out), {
        "source_type": "docx",
        "paragraph_count": len(doc.paragraphs),
        "table_count": len(doc.tables),
    }


# -------------------------------------------------------------------- XLSX


def _ingest_xlsx(data: bytes) -> tuple[str, dict]:
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except Exception as exc:
        raise IngestError(f"could not open XLSX: {exc}") from exc

    out: list[str] = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        out.append(f"<h2>{html_std.escape(sheet_name)}</h2>")
        rows_html = []
        for row in ws.iter_rows(values_only=True):
            cells = "".join(
                f"<td>{html_std.escape(str(c)) if c is not None else ''}</td>"
                for c in row
            )
            rows_html.append(f"<tr>{cells}</tr>")
            if len(rows_html) >= 500:  # safety
                rows_html.append('<tr><td colspan="99">…truncated at 500 rows</td></tr>')
                break
        if rows_html:
            out.append(
                '<table style="border-collapse: collapse; margin: 12pt 0; font-size: 10pt;">'
                + "".join(rows_html)
                + "</table>"
            )

    return "\n".join(out), {
        "source_type": "xlsx",
        "sheet_count": len(wb.sheetnames),
    }


# -------------------------------------------------------------------- TEXT / HTML


def _ingest_text(data: bytes) -> tuple[str, dict]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1", errors="replace")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    out = "\n".join(
        f"<p>{html_std.escape(p).replace(chr(10), '<br>')}</p>"
        for p in paragraphs
    )
    return out, {"source_type": "text", "paragraph_count": len(paragraphs)}


def _ingest_html(data: bytes) -> tuple[str, dict]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1", errors="replace")
    # Intentionally not running a full sanitizer here — the editor
    # surface is contenteditable and we rely on browser DOM parsing
    # to normalize. Callers that accept untrusted HTML should layer
    # bleach or similar before storing.
    return text, {"source_type": "html"}


# -------------------------------------------------------------------- IMAGE


def _mime_for(suffix: str) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".tiff": "image/tiff", ".tif": "image/tiff",
    }.get(suffix, "application/octet-stream")


def _ingest_image(data: bytes, filename: str) -> tuple[str, dict]:
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(data))
        img.verify()  # tamper check; must re-open to use after verify()
        img = Image.open(io.BytesIO(data))
    except Exception as exc:
        raise IngestError(f"could not read image: {exc}") from exc

    width, height = img.size
    suffix = "." + (filename.rsplit(".", 1)[-1].lower() if "." in filename else "")
    mime = _mime_for(suffix)
    b64 = base64.b64encode(data).decode("ascii")
    data_uri = f"data:{mime};base64,{b64}"

    out: list[str] = []
    ocr_text = ""
    ocr_used = False

    if _ocr_available():
        try:
            import pytesseract
            ocr_text = (pytesseract.image_to_string(img) or "").strip()
            ocr_used = True
        except Exception:
            ocr_text = ""
            ocr_used = False

    if ocr_text:
        out.append(
            '<p style="color:#5a6676; font-size:9pt; letter-spacing:0.08em;">'
            "TRANSCRIBED FROM IMAGE</p>"
        )
        for para in ocr_text.split("\n\n"):
            para = para.strip()
            if not para:
                continue
            out.append(f"<p>{html_std.escape(para).replace(chr(10), '<br>')}</p>")
        out.append('<hr style="margin: 18pt 0; border: 0; border-top: 1px dashed #c7ced6;">')
        out.append(
            '<p style="color:#5a6676; font-size:9pt; letter-spacing:0.08em;">'
            "ORIGINAL IMAGE</p>"
        )

    out.append(
        f'<figure style="margin: 12pt 0;">'
        f'<img src="{data_uri}" alt="{html_std.escape(filename)}" '
        f'style="max-width:100%; height:auto;">'
        f'<figcaption style="font-size:9pt; color:#5a6676; margin-top:4pt;">'
        f'{html_std.escape(filename)} — {width}×{height}px</figcaption>'
        f'</figure>'
    )

    return "\n".join(out), {
        "source_type": "image",
        "mime": mime,
        "width": width,
        "height": height,
        "ocr_available": _ocr_available(),
        "ocr_used": ocr_used,
        "ocr_chars": len(ocr_text),
    }
