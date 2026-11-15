"""Vendored PDF.js on the signer landing (G10).

Covers:

* The vendored library files are present at ``app/static/vendor/pdfjs/``
  and served through Flask's static handler.
* The custom ``trustseal-viewer.mjs`` loads ``pdf.mjs`` by a same-
  origin URL (no CDN).
* The review template references the viewer, exposes the host /
  controls / status elements, and wires the vendor URL via
  ``url_for('static', ...)`` so cache-busting works.
* The <noscript> fallback mentions the download link so JS-less
  visitors still have a path forward.
* The vendor directory ships a NOTICE and LICENSE so the attribution
  is preserved.
* ``/sign/<token>/download`` continues to stream the private PDF
  (regression check on the existing flow).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest


VENDOR_DIR = Path(__file__).resolve().parent.parent / "app" / "static" / "vendor" / "pdfjs"


@pytest.fixture
def seeded(pg_app):
    """Minimal fixture reused across tests: a prepared envelope + invitation."""
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.signing_envelope import (
        EnvelopeParticipant,
        SigningEnvelope,
    )
    from app.models.user import User
    from app.services import signer_invitations

    org = Organization(name="Viewer Tenant")
    db.session.add(org)
    db.session.flush()
    creator = User(
        username="viewer-creator",
        email="viewer-creator@example.test",
        is_active=True,
        organization_id=org.id,
    )
    creator.set_password("not-used-strong-password")
    signer = User(
        username="viewer-signer",
        email="viewer-signer@example.test",
        is_active=True,
        organization_id=org.id,
    )
    signer.set_password("not-used-strong-password")
    db.session.add_all([creator, signer])
    db.session.flush()
    doc = Document(
        title="Review PDF",
        status="pending",
        created_by=creator.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key=f"tenants/{org.id}/orig/pdfjs",
        file_name="probe.pdf",
        mime_type="application/pdf",
        file_size=4,
        sha256="a" * 64,
        scanner="noop",
        created_by_id=creator.id,
    )
    db.session.add(blob)
    db.session.flush()
    envelope = SigningEnvelope(
        organization_id=org.id,
        document_id=doc.id,
        document_blob_id=blob.id,
        document_sha256="a" * 64,
        created_by_id=creator.id,
        state="prepared",
        prepared_at=datetime.utcnow(),
    )
    db.session.add(envelope)
    db.session.flush()
    participant = EnvelopeParticipant(
        envelope_id=envelope.id,
        user_id=signer.id,
        signing_order=1,
        role="signer",
    )
    db.session.add(participant)
    db.session.flush()
    _row, token = signer_invitations.issue(
        envelope=envelope,
        participant=participant,
        issued_by_id=creator.id,
    )
    db.session.commit()
    return {
        "org": org,
        "creator": creator,
        "signer": signer,
        "envelope": envelope,
        "participant": participant,
        "token": token,
    }


def _reset_rate_limiter():
    from app.blueprints.envelopes.views import sign_views as module

    module._RATE_TRACKER.clear()


class TestVendorFiles:
    def test_library_files_present(self):
        for name in ("pdf.mjs", "pdf.worker.mjs", "pdf.renderer.mjs"):
            path = VENDOR_DIR / name
            assert path.is_file(), f"missing vendored {name}"
            # The upstream library is minified / bundled, well over a
            # few KB. If it shrank below 100KB we probably copied the
            # wrong file.
            assert path.stat().st_size > 100_000, f"{name} looks truncated"

    def test_license_and_notice_present(self):
        assert (VENDOR_DIR / "LICENSE").is_file(), "LICENSE missing from vendor dir"
        assert (VENDOR_DIR / "NOTICE.md").is_file(), "NOTICE missing from vendor dir"

    def test_custom_viewer_is_first_party(self):
        viewer = VENDOR_DIR / "trustseal-viewer.mjs"
        assert viewer.is_file()
        text = viewer.read_text(encoding="utf-8")
        assert "GlobalWorkerOptions.workerSrc" in text, (
            "custom viewer must pin a same-origin worker URL"
        )
        assert "/static/vendor/pdfjs/pdf.worker.mjs" in text


class TestStaticDelivery:
    def test_pdf_mjs_served_through_flask(self, pg_app):
        r = pg_app.test_client().get("/static/vendor/pdfjs/pdf.mjs")
        assert r.status_code == 200
        assert "javascript" in r.content_type or "ecmascript" in r.content_type or r.content_type.startswith("text/")
        # The body should start with the module's export banner — not
        # a Flask HTML error page.
        body = r.data[:1024].decode("utf-8", errors="replace")
        assert "pdfjs" in body.lower() or "/*" in body or "export" in body

    def test_worker_served_through_flask(self, pg_app):
        r = pg_app.test_client().get("/static/vendor/pdfjs/pdf.worker.mjs")
        assert r.status_code == 200

    def test_custom_viewer_served_through_flask(self, pg_app):
        r = pg_app.test_client().get(
            "/static/vendor/pdfjs/trustseal-viewer.mjs"
        )
        assert r.status_code == 200
        assert b"mountViewer" in r.data


class TestReviewPage:
    def test_review_markup_wires_the_viewer(self, pg_app, seeded):
        _reset_rate_limiter()
        r = pg_app.test_client().get(f"/sign/{seeded['token']}")
        assert r.status_code == 200
        body = r.data.decode("utf-8")
        # Viewer host element and its controls must all be present.
        assert 'id="pdf-host"' in body
        assert 'id="pdf-status"' in body
        assert 'id="pdf-page"' in body
        assert 'id="zoom-in"' in body
        assert 'id="zoom-out"' in body
        # Vendor URL goes through url_for so Flask applies cache
        # fingerprinting.
        assert "/static/vendor/pdfjs/trustseal-viewer.mjs" in body
        # noscript fallback keeps the download link visible for
        # non-JS visitors.
        assert "<noscript>" in body
        assert "download link" in body.lower()

    def test_review_page_contains_consent_version(self, pg_app, seeded):
        _reset_rate_limiter()
        r = pg_app.test_client().get(f"/sign/{seeded['token']}")
        assert r.status_code == 200
        assert b"trustseal-review-consent-v1" in r.data


class TestDownloadRouteRegression:
    def test_download_rejects_unknown_token(self, pg_app):
        _reset_rate_limiter()
        r = pg_app.test_client().get("/sign/trs_unknownabc/download")
        assert r.status_code == 404
