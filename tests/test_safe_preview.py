"""Safe PDF preview (D2).

Service tests:
* ``sanitize`` on a benign PDF returns a byte-string that still
  starts with the PDF magic and ends with %%EOF.
* ``sanitize`` on a PDF whose /Catalog carries an /OpenAction
  returns a copy with /OpenAction stripped.
* ``sanitize`` refuses non-PDF input with ``SafePreviewError``.

HTTP integration:
* ``GET /api/documents/<id>/blobs/<bid>/preview`` returns 200 with
  sanitised bytes when ``SAFE_PREVIEW_ENABLED=True``.
* Refuses with 503 when disabled.
* Non-owner tenant gets 404.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from flask_jwt_extended import create_access_token
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    TextStringObject,
)
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def _benign_pdf() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(72, 720, "Safe preview smoke test")
    c.showPage()
    c.save()
    return buf.getvalue()


def _pdf_with_open_action() -> bytes:
    """Return a PDF whose /Catalog carries an /OpenAction JS entry."""
    source = PdfReader(io.BytesIO(_benign_pdf()))
    writer = PdfWriter()
    for page in source.pages:
        writer.add_page(page)
    js_action = DictionaryObject(
        {
            NameObject("/S"): NameObject("/JavaScript"),
            NameObject("/JS"): TextStringObject("app.alert('pwn');"),
        }
    )
    writer._root_object[NameObject("/OpenAction")] = js_action
    writer._root_object[NameObject("/JavaScript")] = TextStringObject("evil")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


class TestSanitize:
    def test_benign_pdf_round_trip(self):
        from app.services.documents.safe_preview import sanitize

        result = sanitize(_benign_pdf())
        assert result.startswith(b"%PDF-")
        assert b"%%EOF" in result[-1024:]

    def test_strips_open_action(self):
        from app.services.documents.safe_preview import sanitize

        hostile = _pdf_with_open_action()
        clean = sanitize(hostile)
        reader = PdfReader(io.BytesIO(clean))
        # Both active-content entries removed.
        assert "/OpenAction" not in reader.trailer["/Root"]
        assert "/JavaScript" not in reader.trailer["/Root"]

    def test_refuses_non_pdf(self):
        from app.services.documents.safe_preview import (
            SafePreviewError,
            sanitize,
        )

        with pytest.raises(SafePreviewError):
            sanitize(b"this is not a pdf")


@pytest.fixture
def _enabled_preview(pg_app):
    pg_app.config["SAFE_PREVIEW_ENABLED"] = True
    yield pg_app
    pg_app.config["SAFE_PREVIEW_ENABLED"] = False


@pytest.fixture
def seeded(pg_app, tmp_path):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.user import User

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)

    org = Organization(name="Preview Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    owner = User(
        username="preview-owner",
        email="preview-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("previewpassword12345")
    intruder_org = Organization(name="Other Preview", type="company")
    db.session.add(intruder_org)
    db.session.flush()
    intruder = User(
        username="preview-intruder",
        email="preview-intruder@example.test",
        is_active=True,
        organization_id=intruder_org.id,
    )
    intruder.set_password("previewpassword12345")
    db.session.add_all([owner, intruder])
    db.session.flush()

    doc = Document(
        title="Preview doc",
        status="draft",
        created_by=owner.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()

    pdf = _pdf_with_open_action()
    import hashlib

    digest = hashlib.sha256(pdf).hexdigest()
    key = f"{digest}.pdf"
    (Path(private_root) / key).write_bytes(pdf)
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key=key,
        file_name="hostile.pdf",
        mime_type="application/pdf",
        file_size=len(pdf),
        sha256=digest,
        scanner="noop-scanner",
        created_by_id=owner.id,
    )
    db.session.add(blob)
    db.session.commit()
    return {
        "org": org,
        "owner": owner,
        "intruder": intruder,
        "doc": doc,
        "blob": blob,
    }


class TestApi:
    def test_preview_returns_sanitised_bytes(
        self, _enabled_preview, seeded
    ):
        client = _enabled_preview.test_client()
        token = create_access_token(identity=str(seeded["owner"].id))
        r = client.get(
            f"/api/documents/{seeded['doc'].id}/blobs/{seeded['blob'].id}/preview",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        assert r.mimetype == "application/pdf"
        body = r.get_data()
        assert body.startswith(b"%PDF-")
        reader = PdfReader(io.BytesIO(body))
        assert "/OpenAction" not in reader.trailer["/Root"]

    def test_preview_refused_when_disabled(self, pg_app, seeded):
        pg_app.config["SAFE_PREVIEW_ENABLED"] = False
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["owner"].id))
        r = client.get(
            f"/api/documents/{seeded['doc'].id}/blobs/{seeded['blob'].id}/preview",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 503

    def test_foreign_tenant_is_404(self, _enabled_preview, seeded):
        client = _enabled_preview.test_client()
        token = create_access_token(identity=str(seeded["intruder"].id))
        r = client.get(
            f"/api/documents/{seeded['doc'].id}/blobs/{seeded['blob'].id}/preview",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404
