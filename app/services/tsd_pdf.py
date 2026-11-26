"""Render a TrustSeal Document to PDF.

The decrypted HTML is passed through ``xhtml2pdf`` which runs on
ReportLab under the hood — pure-Python, no native dependencies. Supports
standard international & legal paper sizes (A4, US Letter, US Legal, A5,
Executive, B5), Portrait/Landscape orientation, custom margins, and
automatic detection of letterhead paper metadata embedded in the HTML.
"""
from __future__ import annotations

import html as html_std
import io
import re
import secrets
from datetime import datetime, timezone
from typing import Optional


class PdfExportError(RuntimeError):
    """Domain-level PDF-export failure (render or encryption)."""


_PAGE_SIZE_CSS: dict[str, str] = {
    "a4": "A4",
    "letter": "Letter",
    "legal": "Legal",
    "a5": "A5",
    "executive": "184.15mm 266.7mm",
    "b5": "176mm 250mm",
}


def _build_wrapper_css(
    page_size: str = "a4",
    orientation: str = "portrait",
    margin_mm: int = 22,
    margin_top_mm: Optional[int] = None,
    margin_bottom_mm: Optional[int] = None,
    extra_css: str = "",
    include_default_footer: bool = True,
) -> str:
    sz_key = (page_size or "a4").strip().lower()
    css_size = _PAGE_SIZE_CSS.get(sz_key, "A4")
    orient = "landscape" if (orientation or "").strip().lower() == "landscape" else "portrait"
    # xhtml2pdf supports "A4 landscape" or explicit "297mm 210mm"
    if orient == "landscape":
        if " " in css_size:
            w, h = css_size.split(" ", 1)
            size_decl = f"{h} {w}"
        else:
            size_decl = f"{css_size} landscape"
    else:
        size_decl = css_size
    m = max(10, min(40, int(margin_mm or 22)))
    m_top = max(10, min(110, int(margin_top_mm))) if margin_top_mm is not None else m
    m_bot = max(10, min(70, int(margin_bottom_mm))) if margin_bottom_mm is not None else (m + 4)
    footer_frame_css = (
        f"""
  @frame footer_frame {{
    -pdf-frame-content: footer_content;
    left: {m}mm; right: {m}mm;
    bottom: 8mm; height: 8mm;
  }}"""
        if include_default_footer
        else ""
    )
    return f"""
@page {{
  size: {size_decl};
  margin: {m_top}mm {m}mm {m_bot}mm {m}mm;{footer_frame_css}
}}
body {{ font-family: Helvetica, Arial, sans-serif; font-size: 10.5pt; line-height: 1.5; color: #121a26; }}
h1 {{ font-size: 19pt; font-weight: bold; margin: 16pt 0 9pt; color: #121a26; }}
h2 {{ font-size: 14pt; font-weight: bold; margin: 14pt 0 7pt; color: #121a26; }}
h3 {{ font-size: 11.5pt; font-weight: bold; margin: 11pt 0 5pt; color: #121a26; }}
p  {{ margin: 0 0 9pt; }}
blockquote {{ margin: 0 0 9pt; padding-left: 12pt; border-left: 2pt solid #c7ced6; color: #5a6676; font-style: italic; }}
pre, code {{ font-family: Courier, monospace; font-size: 9pt; }}
ul, ol {{ padding-left: 18pt; margin: 0 0 9pt; }}
a {{ color: #0f3b82; text-decoration: underline; }}
img {{ max-width: 100%; }}
.tsd-footer {{ font-size: 7.5pt; color: #5a6676; text-align: center; }}
.tsd-footer strong {{ color: #0f3b82; }}
{extra_css}
"""


def _detect_html_page_meta(html_src: str) -> tuple[Optional[str], Optional[str], Optional[int]]:
    """Read optional data-paper-size / data-orientation / data-margin-mm from letterhead header."""
    if not html_src:
        return None, None, None
    ps = re.search(r'data-paper-size="([a-z0-9]+)"', html_src, re.I)
    ori = re.search(r'data-orientation="(portrait|landscape)"', html_src, re.I)
    mg = re.search(r'data-margin-mm="(\d+)"', html_src, re.I)
    return (
        ps.group(1).lower() if ps else None,
        ori.group(1).lower() if ori else None,
        int(mg.group(1)) if mg else None,
    )


def _footer_block(*, document_id: int, version: int, tenant_id: int, exported_at: datetime) -> str:
    return (
        f'<div id="footer_content" class="tsd-footer">'
        f'<strong>TRUSTSEAL</strong> Document '
        f'#{document_id} · v{version} · tenant {tenant_id} · '
        f'exported {exported_at.strftime("%Y-%m-%d %H:%M UTC")}'
        f'</div>'
    )


def render_html_to_pdf(
    *,
    html: str,
    title: str,
    document_id: int,
    version: int,
    tenant_id: int,
    user_password: Optional[str] = None,
    owner_password: Optional[str] = None,
    page_size: Optional[str] = None,
    orientation: Optional[str] = None,
    margin_mm: Optional[int] = None,
    margin_top_mm: Optional[int] = None,
    margin_bottom_mm: Optional[int] = None,
    extra_css: str = "",
    include_default_footer: bool = True,
) -> bytes:
    """Render decrypted HTML to PDF bytes, optionally encrypted."""
    from xhtml2pdf import pisa
    from app.services.placeholder_engine import build_placeholder_context, resolve_placeholders_for_export

    resolved_html = resolve_placeholders_for_export(
        html or "<p></p>",
        build_placeholder_context(
            extra={
                "document_ref": f"TSD-{int(document_id):05d}" if document_id else "",
                "document_title": title or "",
            }
        ),
    )

    det_ps, det_ori, det_mg = _detect_html_page_meta(resolved_html)
    eff_size = page_size or det_ps or "a4"
    eff_orient = orientation or det_ori or "portrait"
    eff_margin = margin_mm if margin_mm is not None else (det_mg if det_mg is not None else 22)

    exported_at = datetime.now(timezone.utc)
    wrapper_css = _build_wrapper_css(
        page_size=eff_size,
        orientation=eff_orient,
        margin_mm=eff_margin,
        margin_top_mm=margin_top_mm,
        margin_bottom_mm=margin_bottom_mm,
        extra_css=extra_css,
        include_default_footer=include_default_footer,
    )
    footer_html = (
        _footer_block(document_id=document_id, version=version, tenant_id=tenant_id, exported_at=exported_at)
        if include_default_footer
        else ""
    )
    doc_html = (
        f'<html><head>'
        f'<title>{html_std.escape(title)}</title>'
        f'<style>{wrapper_css}</style></head>'
        f'<body>{resolved_html or "<p></p>"}'
        f'{footer_html}'
        f'</body></html>'
    )

    buf = io.BytesIO()
    result = pisa.CreatePDF(doc_html, dest=buf)
    if result.err:
        raise PdfExportError(f"xhtml2pdf failed with {result.err} error(s)")
    pdf_bytes = buf.getvalue()

    if user_password is None:
        return pdf_bytes

    try:
        from pypdf import PdfReader, PdfWriter
    except Exception as exc:
        raise PdfExportError(f"pypdf not available for encryption: {exc}") from exc

    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter(clone_from=reader)
    owner = owner_password or secrets.token_urlsafe(24)
    try:
        writer.encrypt(
            user_password=user_password,
            owner_password=owner,
            use_128bit=True,
            permissions_flag=0b0100,
        )
    except TypeError:
        writer.encrypt(user_password, owner, use_128bit=True)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
