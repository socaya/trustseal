"""Regression tests for interim centralized API authorization.

Run with: python -m pytest tests/test_api_security_policy.py -q
These tests require the Flask application dependencies to be installed.
"""
from unittest.mock import patch

import pytest
from flask import Flask
from werkzeug.exceptions import HTTPException

from app.policies.api_access import enforce_legacy_api_security

app = Flask(__name__)


def check(path, method="GET", admin=False):
    with app.test_request_context(path, method=method):
        with patch("app.policies.api_access.verify_jwt_in_request") as verify:
            with patch("app.policies.api_access.get_jwt_identity", return_value="42"):
                with patch("app.policies.api_access.is_admin", return_value=admin):
                    try:
                        enforce_legacy_api_security()
                        return None, verify.called
                    except HTTPException as exc:
                        return exc.code, verify.called


@pytest.mark.parametrize("path", ["/api/auth/login", "/api/auth/register"])
def test_public_auth_routes(path):
    assert check(path, "POST") == (None, False)


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize(
    "path",
    [
        "/api/document-signatures/",
        "/api/document-signatures/12",
        "/api/signature-requests/3",
        "/api/payments",
    ],
)
def test_unverified_trust_and_payment_mutations_blocked(path, method):
    assert check(path, method, admin=True) == (409, True)


@pytest.mark.parametrize(
    "path",
    [
        "/api/users",
        "/api/users/6/roles",
        "/api/roles/3/permissions",
        "/api/settings",
        "/api/invitations",
    ],
)
def test_non_admin_denied_privileged_routes(path):
    assert check(path) == (403, True)


def test_admin_can_read_roles():
    assert check("/api/roles", admin=True) == (None, True)


def test_document_api_requires_jwt():
    assert check("/api/documents/mine") == (None, True)


def test_non_admin_cannot_read_all_signature_profiles():
    assert check("/api/signature-profiles") == (403, True)


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize(
    "path",
    ["/api/stamps", "/api/api/stamps", "/api/api/templates", "/api/usages"],
)
def test_legacy_stamp_routes_retired_without_generic_access(path, method):
    assert check(path, method, admin=True) == (410, False)


def test_governed_stamp_api_keeps_jwt_authorization():
    assert check("/api/stamp-custody") == (None, True)


def test_anonymous_uploaded_pdf_verification_is_public():
    assert check("/api/public-verification/pdf", "POST") == (None, False)
