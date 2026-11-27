"""Interim deny-by-default guard for legacy API routes.

Transport protection is not a substitute for per-resource policies. Until
those policies exist, block unsupported trust-critical and billing mutations.
"""
import re

from flask import abort, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from flask_login import current_user

from app.extensions import db
from app.models.system import Role, UserRole

# API prefixes that are designed to be called from first-party authenticated
# browser sessions (not just JWT-bearing API clients). Each endpoint still
# authenticates and authorizes internally — this list only lets session
# traffic through the blanket ``verify_jwt_in_request`` guard below.
SESSION_AUTH_ALLOWED_PREFIXES = (
    "/api/tsd",
    "/api/tsd-stamps",
    "/api/media-library",
    "/api/letterheads",
    "/api/signatures",
    "/api/contracts",
    "/api/projects",
    "/api/portfolios",
    "/api/programmes",
    "/api/project-intakes",
    "/api/resources",
    "/api/timesheets",
    "/api/project-templates",
    "/api/contract-templates",
)

PUBLIC_ENDPOINTS = frozenset((
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/password-reset/request",
))
# Email-verification and password-reset consume routes authenticate
# the caller by validating a one-shot token inside the handler.
PUBLIC_PREFIXES = (
    "/api/auth/verify-email/",
    "/api/auth/password-reset/",
    "/api/project-portal/",
)
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
PRIVILEGED_ROLE_NAMES = frozenset(("admin", "administrator", "superadmin", "super_admin", "platform_admin", "ts_platform_admin"))
PLATFORM_ADMIN_ROLE_NAMES = frozenset(("superadmin", "super_admin", "platform_admin", "ts_platform_admin"))
ORG_ADMIN_ROLE_NAMES = frozenset(("admin", "administrator", "org_admin", "organization_admin", "owner")) | PLATFORM_ADMIN_ROLE_NAMES


def _under(path, prefix):
    return path == prefix or path.startswith(prefix + "/")


def is_admin(user_id):
    rows = db.session.query(Role.name).join(
        UserRole, UserRole.role_id == Role.id
    ).filter(UserRole.user_id == user_id).all()
    return any(name and name.strip().lower() in PRIVILEGED_ROLE_NAMES for (name,) in rows)


def get_user_nav_roles(user) -> dict:
    """Return role visibility flags for the 3-tier sidebar navigation.

    - Subscriber Member: nav_is_org_admin=False, nav_is_platform_admin=False
    - Organization Admin: nav_is_org_admin=True, nav_is_platform_admin=False
    - TS Platform Admin: nav_is_org_admin=True, nav_is_platform_admin=True
    """
    if not user or not getattr(user, "is_authenticated", False):
        return {"nav_is_org_admin": False, "nav_is_platform_admin": False}
    try:
        rows = db.session.query(Role.name).join(
            UserRole, UserRole.role_id == Role.id
        ).filter(UserRole.user_id == user.id).all()
        names = {name.strip().lower() for (name,) in rows if name}
    except Exception:
        names = set()
    is_plat = bool(names & PLATFORM_ADMIN_ROLE_NAMES)
    is_org = bool(names & ORG_ADMIN_ROLE_NAMES)
    # Primary platform administrator / seeded system admin (org 1 + admin role or admin@trustseal.local)
    email = (getattr(user, "email", "") or "").strip().lower()
    if not is_plat and (email == "admin@trustseal.local" or (is_org and getattr(user, "organization_id", None) == 1 and "admin" in names)):
        is_plat = True
        is_org = True
    return {"nav_is_org_admin": is_org or is_plat, "nav_is_platform_admin": is_plat}


def enforce_legacy_api_security():
    """Authenticate API requests and restrict operations lacking domain policies."""
    path = request.path.rstrip("/") or "/"
    if not _under(path, "/api"):
        return
    if path in PUBLIC_ENDPOINTS:
        return
    if any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
        return
    # Upload-only verification is independent of private accounts and records.
    if path == "/api/public-verification/pdf" and request.method == "POST":
        return
    # Refresh-token decorators validate their own JWT type and revocation.
    if path == "/api/auth/refresh":
        return
    # Self-service password change is authenticated per-user inside the
    # view.
    if path == "/api/auth/change-password":
        verify_jwt_in_request()
        return
    # Published OpenAPI document is intentionally public.
    if path == "/api/openapi.json" and request.method == "GET":
        return
    # The old stamp and template APIs exposed unscoped tenant records and
    # generic updates. Require the governed /api/stamp-custody workflow.
    if any(_under(path, prefix) for prefix in LEGACY_STAMP_PREFIXES):
        abort(410, description="Legacy stamp API retired; use stamp custody workflow")
    # First-party browser calls (editor, inspector): allow session auth as
    # a substitute for JWT. The route still runs its own @login_required
    # and tenant checks. Mutating verbs must present a same-origin
    # ``X-Requested-With: fetch`` header OR a matching session CSRF
    # token so cross-origin pages can't forge requests against the
    # editor APIs.
    if any(_under(path, prefix) for prefix in SESSION_AUTH_ALLOWED_PREFIXES):
        if current_user.is_authenticated:
            if request.method in ("POST", "PUT", "PATCH", "DELETE"):
                xrw = request.headers.get("X-Requested-With", "")
                if xrw.lower() not in ("fetch", "xmlhttprequest"):
                    abort(403, description="missing X-Requested-With header")
            return
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
