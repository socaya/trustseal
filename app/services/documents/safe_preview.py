"""Server-side PDF sanitiser for preview delivery.

Before a browser renders a stored PDF, this service strips the most
common active-content vectors so a preview of a hostile file cannot
execute code inside a user's session:

* Document-level open action (/OpenAction) — can trigger JS on load.
* Document-level additional actions (/AA) — same category.
* Any /JS or /JavaScript entries in named destinations.
* Embedded files (/EmbeddedFiles) — PDF polyglots and nested
  payloads.
* Per-page /AA (page open / close additional actions).
* Field actions on form widgets (/AA on annotations).

The sanitiser is **not** a substitute for malware scanning; it only
removes the vectors that would otherwise run inside the PDF viewer
when previewed. The caller still routes the file through the
antivirus pipeline before the stored object is served.

Implementation uses pypdf which lets us walk the object graph and
remove problematic dictionary entries. The output is a new PDF
written to memory. The original stored object is never mutated.
"""
from __future__ import annotations

import io
from typing import Mapping

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject


class SafePreviewError(RuntimeError):
    """Raised when the source PDF cannot be parsed or sanitised."""


REMOVE_FROM_CATALOG = (
    NameObject("/OpenAction"),
    NameObject("/AA"),
    NameObject("/Names"),
    NameObject("/JavaScript"),
    NameObject("/JS"),
    NameObject("/AcroForm"),
)
REMOVE_FROM_PAGE = (
    NameObject("/AA"),
)
REMOVE_FROM_ANNOT = (
    NameObject("/AA"),
    NameObject("/A"),
    NameObject("/JS"),
)


def enabled(config: Mapping) -> bool:
    return bool(config.get("SAFE_PREVIEW_ENABLED"))


def sanitize(payload: bytes) -> bytes:
    """Return a sanitised PDF byte-string.

    Raises :class:`SafePreviewError` for malformed input.
    """
    if not isinstance(payload, (bytes, bytearray)):
        raise SafePreviewError("payload_type_invalid")
    if not payload.startswith(b"%PDF-"):
        raise SafePreviewError("payload_missing_pdf_header")
    try:
        reader = PdfReader(io.BytesIO(payload), strict=False)
    except Exception as exc:  # pragma: no cover - defensive
        raise SafePreviewError("payload_unparseable") from exc
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    # Scrub the copied catalog.
    catalog = writer._root_object
    for key in REMOVE_FROM_CATALOG:
        if key in catalog:
            del catalog[key]
    # Scrub each copied page.
    for page in writer.pages:
        for key in REMOVE_FROM_PAGE:
            if key in page:
                del page[key]
        annots = page.get("/Annots")
        if annots is not None:
            try:
                for annot_ref in list(annots):
                    try:
                        annot = annot_ref.get_object()
                    except Exception:
                        continue
                    for key in REMOVE_FROM_ANNOT:
                        if key in annot:
                            del annot[key]
            except TypeError:
                # Annots may be a direct array or an indirect reference;
                # either way, scrubbing every annotation that can be
                # resolved is the goal.
                pass
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
