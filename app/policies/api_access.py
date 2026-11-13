"""Interim deny-by-default guard for legacy API routes.

Transport protection is not a substitute for per-resource policies. Until
those policies exist, block unsupported trust-critical and billing mutations.
"""
import re

from flask import abort, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.extensions import db
from app.models.system import Role, UserRole

PUBLIC_ENDPOINTS = frozenset(("/api/auth/login", "/api/auth/register"))
ADMIN_EXACT = frozenset((
    "/api/roles", "/api/permissions", "/api/settings", "/api/audit-logs",
    "/api/role-permissions", "/api/user-roles", "/api/invitations",
))
ADMIN_PREFIXES = (
    "/api/roles/", "/api/permissions/", "/api/settings/",
    "/api/audit-logs/", "/api/role-permissions/", "/api/user-roles/",
)
LEGACY_STAMP_PREFIXES = (
    "/api/stamps", "/api/usages", "/api/api/stamps",
    "/api/api/usages", "/api/api/templates",
)
TRUST_CRITICAL_PREFIXES = (
    "/api/document-signatures", "/api/signature-requests",
    "/api/stamps", "/api/usages", "/api/payments",
)
PRIVILEGED_ROLE_NAMES = frozenset(("admin", "administrator", "superadmin", "super_admin"))


def _under(path, prefix):
    return path == prefix or path.startswith(prefix + "/")


def is_admin(user_id):
    rows = db.session.query(Role.name).join(
        UserRole, UserRole.role_id == Role.id
    ).filter(UserRole.user_id == user_id).all()
    return any(name and name.strip().lower() in PRIVILEGED_ROLE_NAMES for (name,) in rows)


def enforce_legacy_api_security():
    """Authenticate API requests and restrict operations lacking domain policies."""
    path = request.path.rstrip("/") or "/"
    if not _under(path, "/api"):
        return
    if path in PUBLIC_ENDPOINTS:
        return
    # Upload-only verification is independent of private accounts and records.
    if path == "/api/public-verification/pdf" and request.method == "POST":
        return
    # Refresh-token decorators validate their own JWT type and revocation.
    if path == "/api/auth/refresh":
        return
    # The old stamp and template APIs exposed unscoped tenant records and
    # generic updates. Require the governed /api/stamp-custody workflow.
    if any(_under(path, prefix) for prefix in LEGACY_STAMP_PREFIXES):
        abort(410, description="Legacy stamp API retired; use stamp custody workflow")
    verify_jwt_in_request()
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        abort(401)

    # Existing generic CRUD cannot create valid trust or billing evidence.
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if any(_under(path, prefix) for prefix in TRUST_CRITICAL_PREFIXES):
            abort(409, description="Verified domain workflow required")

    # Sensitive legacy collections should not leak all tenants' records.
    if request.method in ("GET", "HEAD") and any(
        _under(path, prefix) for prefix in (
            "/api/document-signatures", "/api/signature-requests",
            "/api/signature-profiles", "/api/stamps", "/api/usages",
            "/api/payments", "/api/invitations",
        )
    ):
        if not is_admin(user_id):
            abort(403)

    # CRUD users, global role assignments and platform settings are platform-admin only.
    require_admin = (
        path in ADMIN_EXACT
        or any(path.startswith(prefix) for prefix in ADMIN_PREFIXES)
        or _under(path, "/api/users")
        or (_under(path, "/api/organizations") and request.method != "GET")
        or _under(path, "/api/subscriptions")
        or _under(path, "/api/subscription-plans")
    )
    if require_admin and not is_admin(user_id):
        abort(403)
