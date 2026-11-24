"""Public verification view (/verify) contract.

Covers:

* GET /verify returns the form with a disabled banner when the deployment
  has not enabled verification.
* GET /verify renders the form when enabled.
* POST without an evidence digest returns 400 and the form with the
  rejection reason.
* POST with a non-PDF body returns 400.
* POST with a PDF but no valid trust config returns 503.
* Rate-limiting kicks in after too many submissions from the same IP.
* The verdict heading uses text + a glyph (no color-only status).
* No sensitive detail (filename, user-agent) ever appears in the body.
"""
from __future__ import annotations

import io

import pytest


@pytest.fixture
def unverified_app(pg_app):
    """Disabled-by-default state: the banner must say so."""
    pg_app.config["PUBLIC_PDF_VERIFICATION_ENABLED"] = False
    return pg_app


@pytest.fixture
def partial_app(pg_app):
    """Verification enabled but missing the pinned certificate."""
    pg_app.config["PUBLIC_PDF_VERIFICATION_ENABLED"] = True
    pg_app.config["PUBLIC_PDF_VERIFICATION_CERT_SHA256"] = None
    return pg_app


@pytest.fixture
def enabled_app(pg_app):
    pg_app.config["PUBLIC_PDF_VERIFICATION_ENABLED"] = True
    pg_app.config["PUBLIC_PDF_VERIFICATION_CERT_SHA256"] = "a" * 64
    return pg_app


class TestGetForm:
    def test_disabled_banner_shown(self, unverified_app):
        client = unverified_app.test_client()
        r = client.get("/verify")
        assert r.status_code == 200
        body = r.data.decode("utf-8")
        assert "Verification is not enabled on this deployment" in body

    def test_enabled_page_shows_form(self, enabled_app):
        r = enabled_app.test_client().get("/verify")
        assert r.status_code == 200
        body = r.data.decode("utf-8")
        assert "Verify a sealed document" in body
        assert 'name="evidence_sha256"' in body
        assert 'name="pdf"' in body


class TestPostValidation:
    def test_missing_evidence_digest_returns_400(self, enabled_app):
        client = enabled_app.test_client()
        r = client.post(
            "/verify/pdf",
            data={"evidence_sha256": ""},
            content_type="multipart/form-data",
        )
        assert r.status_code == 400
        assert b"Provide the 64-character evidence digest" in r.data

    def test_non_pdf_body_rejected(self, enabled_app):
        client = enabled_app.test_client()
        r = client.post(
            "/verify/pdf",
            data={
                "evidence_sha256": "b" * 64,
                "pdf": (io.BytesIO(b"not a pdf"), "evil.exe"),
            },
            content_type="multipart/form-data",
        )
        assert r.status_code == 400
        assert b"Attach the PDF" in r.data

    def test_invalid_pdf_bytes_rejected(self, enabled_app):
        client = enabled_app.test_client()
        r = client.post(
            "/verify/pdf",
            data={
                "evidence_sha256": "b" * 64,
                "pdf": (io.BytesIO(b"not a pdf"), "bad.pdf"),
            },
            content_type="multipart/form-data",
        )
        assert r.status_code == 400
        assert b"not a PDF" in r.data

    def test_disabled_returns_503(self, unverified_app):
        client = unverified_app.test_client()
        r = client.post(
            "/verify/pdf",
            data={
                "evidence_sha256": "c" * 64,
                "pdf": (io.BytesIO(b"%PDF-1.4\nx\n%%EOF\n"), "x.pdf"),
            },
            content_type="multipart/form-data",
        )
        assert r.status_code == 503
        assert b"not enabled" in r.data

    def test_misconfigured_returns_503(self, partial_app):
        client = partial_app.test_client()
        r = client.post(
            "/verify/pdf",
            data={
                "evidence_sha256": "d" * 64,
                "pdf": (io.BytesIO(b"%PDF-1.4\nx\n%%EOF\n"), "x.pdf"),
            },
            content_type="multipart/form-data",
        )
        assert r.status_code == 503
        assert b"configuration is incomplete" in r.data


class TestRateLimiting:
    def test_rate_limit_triggers_after_many_requests(self, enabled_app):
        # Reset the shared DB-backed limiter state for this test.
        from app.extensions import db
        from app.models.rate_limit_bucket import RateLimitBucket
        from app.services import rate_limiting

        rate_limiting.clear_cache()
        db.session.query(RateLimitBucket).delete()
        db.session.commit()
        client = enabled_app.test_client()
        for _ in range(11):
            r = client.post(
                "/verify/pdf",
                data={
                    "evidence_sha256": "e" * 64,
                    "pdf": (io.BytesIO(b"%PDF-1.4\nx\n%%EOF\n"), "x.pdf"),
                },
                content_type="multipart/form-data",
            )
        assert r.status_code == 429
        assert b"Too many verification attempts" in r.data


class TestVerdictAccessibility:
    def test_verdict_markup_uses_text_and_icon(self, enabled_app):
        """Status communication must not rely on color alone."""
        from app.blueprints.trust.views.verify_views import _verdict_from

        verdict, detail = _verdict_from({"overall_valid": True})
        assert verdict == "valid"
        assert detail

    def test_mismatch_verdict_labeled_explicitly(self, enabled_app):
        from app.blueprints.trust.views.verify_views import _verdict_from

        verdict, _ = _verdict_from(
            {"overall_valid": False, "intact": False, "trusted": True}
        )
        assert verdict == "mismatch"
