"""Image → PDF ingestion (D1).

Covers:

Service layer (:mod:`app.services.documents.image_conversion`):
* ``detect_format`` returns ``png`` / ``jpeg`` on valid magic.
* ``detect_format`` refuses files that start with neither magic.
* ``convert_to_pdf`` returns a byte-string that starts with the PDF
  header and contains the EOF marker.
* ``convert_to_pdf`` refuses when ``IMAGE_PDF_CONVERSION_ENABLED`` is
  false (default), when payload is empty, when payload is too large,
  when pixel count exceeds the cap.
* RGBA PNG is flattened onto a white background (no exception).

HTTP integration (:mod:`app.blueprints.documents.api.document_api`):
* ``POST /api/documents/<id>/images`` ingests a PNG and creates a
  ``DocumentBlob`` whose stored object has the PDF magic.
* Non-image upload rejected with 400.
* Non-owner receives 404.

The scanner is monkey-patched to a no-op (identical to the pattern
used by ``tests/test_private_document_storage.py``) so the test
suite runs without a local clamav binary.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from flask_jwt_extended import create_access_token

from PIL import Image


@pytest.fixture
def _enabled(pg_app):
    pg_app.config["IMAGE_PDF_CONVERSION_ENABLED"] = True
    pg_app.config["IMAGE_CONVERSION_MAX_BYTES"] = 25 * 1024 * 1024
    pg_app.config["IMAGE_CONVERSION_MAX_PIXELS"] = 50_000_000
    yield pg_app
    pg_app.config["IMAGE_PDF_CONVERSION_ENABLED"] = False
    pg_app.config["IMAGE_CONVERSION_MAX_BYTES"] = 25 * 1024 * 1024
    pg_app.config["IMAGE_CONVERSION_MAX_PIXELS"] = 50_000_000


@pytest.fixture
def private_root(pg_app, tmp_path):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(root)
    return root


@pytest.fixture
def noop_scanner(monkeypatch):
    from app.services.documents import private_storage

    monkeypatch.setattr(
        private_storage,
        "_scan_pdf",
        lambda path, config: "noop-scanner-test-only",
    )
    yield


@pytest.fixture
def owner(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.user import User

    org = Organization(name="Image Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    user = User(
        username="image-owner",
        email="image-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    user.set_password("imagepassword12345")
    db.session.add(user)
    db.session.commit()
    return user


def _png_bytes(size=(200, 120), *, mode="RGB"):
    img = Image.new(mode, size, (240, 200, 80) if mode == "RGB" else (240, 200, 80, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes(size=(200, 120)):
    img = Image.new("RGB", size, (90, 160, 220))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


class TestDetectFormat:
    def test_png_magic(self):
        from app.services.documents.image_conversion import detect_format

        assert detect_format(_png_bytes()) == "png"

    def test_jpeg_magic(self):
        from app.services.documents.image_conversion import detect_format

        assert detect_format(_jpeg_bytes()) == "jpeg"

    def test_refuses_random_bytes(self):
        from app.services.documents.image_conversion import (
            ImageConversionError,
            detect_format,
        )

        with pytest.raises(ImageConversionError):
            detect_format(b"GIF89a-not-supported-" + b"\0" * 100)


class TestConvertToPdf:
    def test_png_round_trip_yields_pdf(self, _enabled):
        from app.services.documents.image_conversion import convert_to_pdf

        pdf = convert_to_pdf(_png_bytes(), config=_enabled.config)
        assert pdf.startswith(b"%PDF-")
        assert b"%%EOF" in pdf[-1024:]

    def test_rgba_png_is_flattened(self, _enabled):
        from app.services.documents.image_conversion import convert_to_pdf

        pdf = convert_to_pdf(_png_bytes(mode="RGBA"), config=_enabled.config)
        assert pdf.startswith(b"%PDF-")

    def test_disabled_by_default(self, pg_app):
        from app.services.documents.image_conversion import (
            ImageConversionError,
            convert_to_pdf,
        )

        with pytest.raises(ImageConversionError):
            convert_to_pdf(_png_bytes(), config=pg_app.config)

    def test_rejects_empty(self, _enabled):
        from app.services.documents.image_conversion import (
            ImageConversionError,
            convert_to_pdf,
        )

        with pytest.raises(ImageConversionError):
            convert_to_pdf(b"", config=_enabled.config)

    def test_rejects_oversized(self, _enabled):
        from app.services.documents.image_conversion import (
            ImageConversionError,
            convert_to_pdf,
        )

        _enabled.config["IMAGE_CONVERSION_MAX_BYTES"] = 100
        with pytest.raises(ImageConversionError):
            convert_to_pdf(_png_bytes((500, 500)), config=_enabled.config)

    def test_rejects_too_many_pixels(self, _enabled):
        from app.services.documents.image_conversion import (
            ImageConversionError,
            convert_to_pdf,
        )

        _enabled.config["IMAGE_CONVERSION_MAX_PIXELS"] = 100
        with pytest.raises(ImageConversionError):
            convert_to_pdf(_png_bytes((200, 200)), config=_enabled.config)


class TestApi:
    def test_ingest_png_creates_blob(
        self, _enabled, private_root, noop_scanner, owner
    ):
        from app.extensions import db
        from app.models.documents.document import Document
        from app.models.documents.document_blob import DocumentBlob

        doc = Document(
            title="Image doc",
            status="draft",
            created_by=owner.id,
            organization_id=owner.organization_id,
        )
        db.session.add(doc)
        db.session.commit()
        token = create_access_token(identity=str(owner.id))
        client = _enabled.test_client()
        r = client.post(
            f"/api/documents/{doc.id}/images",
            data={"file": (io.BytesIO(_png_bytes()), "scan.png")},
            content_type="multipart/form-data",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201, r.get_data(as_text=True)
        body = r.get_json()
        assert body["mime_type"] == "application/pdf"
        blob = DocumentBlob.query.filter_by(document_id=doc.id).one()
        stored = Path(private_root) / blob.object_key
        assert stored.exists()
        assert stored.read_bytes().startswith(b"%PDF-")

    def test_non_image_is_400(
        self, _enabled, private_root, noop_scanner, owner
    ):
        from app.extensions import db
        from app.models.documents.document import Document

        doc = Document(
            title="Non-image",
            status="draft",
            created_by=owner.id,
            organization_id=owner.organization_id,
        )
        db.session.add(doc)
        db.session.commit()
        token = create_access_token(identity=str(owner.id))
        client = _enabled.test_client()
        r = client.post(
            f"/api/documents/{doc.id}/images",
            data={"file": (io.BytesIO(b"totally not an image"), "not.png")},
            content_type="multipart/form-data",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400

    def test_foreign_owner_is_404(
        self, _enabled, private_root, noop_scanner, owner
    ):
        from app.extensions import db
        from app.models.documents.document import Document
        from app.models.user import User

        intruder = User(
            username="image-intruder",
            email="image-intruder@example.test",
            is_active=True,
            organization_id=owner.organization_id,
        )
        intruder.set_password("imagepassword12345")
        db.session.add(intruder)
        doc = Document(
            title="Not yours",
            status="draft",
            created_by=owner.id,
            organization_id=owner.organization_id,
        )
        db.session.add(doc)
        db.session.commit()
        token = create_access_token(identity=str(intruder.id))
        client = _enabled.test_client()
        r = client.post(
            f"/api/documents/{doc.id}/images",
            data={"file": (io.BytesIO(_png_bytes()), "foreign.png")},
            content_type="multipart/form-data",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404
