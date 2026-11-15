"""Gate high-trust routes behind a verified email address.

Routes that may legitimately send tenant-visible actions downstream
(issue envelopes, approve stamps, invite external signers) refuse
when the authenticated caller has not yet verified ownership of
their declared email. Lower-trust routes (view own documents,
change password, log out) are unaffected.

Usage::

    @bp.route("/do_sensitive")
    @jwt_required()
    @require_verified_email
    def do_sensitive():
        ...

The decorator honors both JWT and Flask-Login authentication.
"""
from __future__ import annotations

from functools import wraps
from typing import Callable

from flask import jsonify, redirect, request, url_for


def require_verified_email(func: Callable) -> Callable:
    """Reject the request if the active user has not verified their email."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        user = _resolve_active_user()
        if user is None:
            return _unverified_response(reason="authentication_required")
        if not getattr(user, "email_verified", False):
            return _unverified_response(reason="email_not_verified")
        return func(*args, **kwargs)

    return wrapper


def _resolve_active_user():
    # Prefer the JWT identity (API callers). Fall back to Flask-Login
    # for session-cookie callers so the decorator applies to HTML
    # views too.
    try:
        from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
        if identity is not None:
            from app.extensions import db
            from app.models.user import User

            user = db.session.get(User, int(identity))
            if user is not None:
                return user
    except Exception:
        pass
    try:
        from flask_login import current_user

        if (
            current_user is not None
            and getattr(current_user, "is_authenticated", False)
        ):
            return current_user
    except Exception:
        pass
    return None


def _unverified_response(*, reason: str):
    if request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
        return (
            jsonify(
                error=reason,
                type=f"https://trustseal.dev/problems/{reason.replace('_', '-')}",
            ),
            403,
        )
    try:
        return redirect(url_for("auth_views.verify_email"))
    except Exception:
        return (
            jsonify(error=reason),
            403,
        )
