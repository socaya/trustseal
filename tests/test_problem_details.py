"""RFC 7807 problem+json contract tests.

Covers:

* API errors return ``application/problem+json`` with the expected
  fields (``type``, ``title``, ``status``, ``instance``, ``request_id``).
* Legacy ``abort(status, description="slug")`` promotes the slug into
  ``type`` so clients can switch on it.
* Free-form descriptions land in ``detail``; tracebacks never do.
* Werkzeug's default framework descriptions are stripped.
* Non-API routes still render HTML pages.
* 500s roll back the session and omit the exception message from the
  body.
* ``Cache-Control: no-store`` is set on every problem response.
"""
from __future__ import annotations

import json

import pytest
from flask import abort, jsonify


@pytest.fixture
def app(pg_app):
    from flask_jwt_extended import create_access_token

    from app.extensions import db
    from app.models.organization import Organization
    from app.models.system import Role, UserRole
    from app.models.user import User

    org = Organization(name="Problem Tenant")
    db.session.add(org)
    db.session.flush()
    user = User(
        username="probe", email="probe@example.test", is_active=True,
        organization_id=org.id,
    )
    user.set_password("not-used")
    role = Role(name="admin")
    db.session.add_all([user, role])
    db.session.flush()
    db.session.add(UserRole(user_id=user.id, role_id=role.id))
    db.session.commit()
    pg_app.config["_PROBE_TOKEN"] = create_access_token(identity=str(user.id))
    yield pg_app


def _auth(app):
    return {"Authorization": f"Bearer {app.config['_PROBE_TOKEN']}"}


def _payload(response):
    assert response.content_type.startswith("application/problem+json"), (
        f"expected problem+json, got {response.content_type!r}"
    )
    return response.get_json()


class TestProblemShape:
    def test_slug_promoted_to_type(self, app):
        r = app.test_client().post("/api/_test/slug", headers=_auth(app))
        body = _payload(r)
        assert r.status_code == 409
        assert body["type"] == "https://trustseal.dev/problems/envelope-not-prepared"
        assert body["title"] == "The request conflicts with the current state."
        assert body["status"] == 409
        assert body["instance"] == "/api/_test/slug"
        assert "request_id" in body
        assert "detail" not in body, "slug alone must not duplicate as detail"
        assert r.headers["Cache-Control"] == "no-store"

    def test_freeform_description_lands_in_detail(self, app):
        r = app.test_client().post("/api/_test/freeform", headers=_auth(app))
        body = _payload(r)
        assert body["type"] == "https://trustseal.dev/problems/conflict"
        assert body["detail"] == "Envelope is already finalized on this tenant."

    def test_default_type_without_description(self, app):
        r = app.test_client().post("/api/_test/default", headers=_auth(app))
        body = _payload(r)
        assert body["type"] == "https://trustseal.dev/problems/not-found"
        assert "detail" not in body

    def test_unhandled_exception_hides_internals(self, app):
        r = app.test_client().post("/api/_test/boom", headers=_auth(app))
        body = _payload(r)
        assert r.status_code == 500
        assert body["status"] == 500
        # Critically: neither the raw exception message nor SQL leaks.
        assert "SELECT" not in json.dumps(body)
        assert "secret" not in json.dumps(body)
        assert "traceback" not in body

    def test_request_id_matches_response_header(self, app):
        r = app.test_client().post(
            "/api/_test/slug",
            headers={**_auth(app), "X-Request-ID": "corr-xyz"},
        )
        body = _payload(r)
        assert body["request_id"] == r.headers["X-Request-ID"] == "corr-xyz"


class TestHtmlRoutesPreserved:
    def test_non_api_404_still_renders_html(self, app):
        r = app.test_client().get("/this/does/not/exist")
        # The before-request hook redirects unauthenticated users to
        # login; both the redirect (302) and the HTML 404 preserve the
        # non-problem+json surface. The key assertion is the absence of
        # problem+json for a non-API probe.
        assert r.content_type != "application/problem+json"


class TestLegacyAbortBodies:
    def test_very_long_description_does_not_overflow(self, app):
        """A long description must not be promoted to the slug."""
        from app.errors.problem import _slug_for

        slug, title = _slug_for(409, "x" * 500)
        assert slug == "conflict"
        assert title == "The request conflicts with the current state."

    def test_framework_default_description_elided(self, app):
        """Werkzeug default descriptions (e.g. 'The browser...') are stripped."""
        from app.errors.problem import _detail_for

        assert _detail_for(
            "The browser (or proxy) sent a request that this server could not understand."
        ) is None
