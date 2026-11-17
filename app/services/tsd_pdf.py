"""Render a TrustSeal Document to PDF.

The decrypted HTML is passed through ``xhtml2pdf`` which runs on
ReportLab under the hood — pure-Python, no native dependencies. The
output PDF can optionally be AES-256 encrypted with a user password
(required to open) and an owner password (required for printing /
copying / modifying). If only a user password is given, the owner
password is generated randomly so permissions are enforced.

A footer with the document id, version, and tenant is drawn by
ReportLab via the ``@page`` CSS block. The footer makes every
exported page attributable without relying on the viewer app.
"""
from __future__ import annotations

import html as html_std
import io
import secrets
from datetime import datetime, timezone
from typing import Optional


class PdfExportError(RuntimeError):
    """Domain-level PDF-export failure (render or encryption)."""


_WRAPPER_CSS = """
@page {
  size: Letter;
  margin: 1in;
  @frame footer_frame {
    -pdf-frame-content: footer_content;
    left: 1in; width: 6.5in;
    bottom: 0.4in; height: 0.3in;
  }
}
body { font-family: Helvetica, Arial, sans-serif; font-size: 11pt; line-height: 1.5; color: #121a26; }
h1 { font-size: 20pt; font-weight: bold; margin: 18pt 0 10pt; color: #121a26; }
h2 { font-size: 15pt; font-weight: bold; margin: 16pt 0 8pt; color: #121a26; }
h3 { font-size: 12pt; font-weight: bold; margin: 12pt 0 6pt; color: #121a26; }
p  { margin: 0 0 10pt; }
blockquote { margin: 0 0 10pt; padding-left: 12pt; border-left: 2pt solid #c7ced6; color: #5a6676; font-style: italic; }
pre, code { font-family: Courier, monospace; font-size: 9pt; }
ul, ol { padding-left: 18pt; margin: 0 0 10pt; }
a { color: #0f3b82; text-decoration: underline; }
img { max-width: 6.5in; }
.tsd-footer { font-size: 8pt; color: #5a6676; text-align: center; }
.tsd-footer strong { color: #0f3b82; }
"""


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
) -> bytes:
    """Render decrypted HTML to PDF bytes, optionally encrypted.

    When ``user_password`` is set, the PDF is encrypted with AES-256 so
    the viewer must supply the password. ``owner_password`` defaults
    to a fresh 24-byte random secret, so operator-level permissions
    (printing, copying) stay revoked unless the caller explicitly
    chooses a shared owner password.
    """
    from xhtml2pdf import pisa

    exported_at = datetime.now(timezone.utc)
    doc_html = (
        f'<html><head>'
        f'<title>{html_std.escape(title)}</title>'
        f'<style>{_WRAPPER_CSS}</style></head>'
        f'<body>{html or "<p></p>"}'
        f'{_footer_block(document_id=document_id, version=version, tenant_id=tenant_id, exported_at=exported_at)}'
        f'</body></html>'
    )

    buf = io.BytesIO()
    result = pisa.CreatePDF(doc_html, dest=buf)
    if result.err:
        raise PdfExportError(f"xhtml2pdf failed with {result.err} error(s)")
    pdf_bytes = buf.getvalue()

    if user_password is None:
        return pdf_bytes

    # Pass the rendered PDF through pypdf to apply AES-256 encryption.
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
            use_128bit=True,       # pypdf will prefer AES-256 if available
            permissions_flag=0b0100,  # print low-res, deny modify/copy
        )
    except TypeError:
        # Older pypdf API
        writer.encrypt(user_password, owner, use_128bit=True)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
