"""Step-up MFA guard for high-risk actions.

A caller authenticated with username+password alone is not enough for
actions that materially change trust state: envelope finalization,
stamp approval, admin role grants. Those routes require a **recent**
MFA assertion — the user must have presented their TOTP within the
last few minutes.

Flow:

1. The access token carries an ``mfa_verified_at`` claim (seconds
   since epoch) when the user has recently completed MFA.
2. The ``@require_recent_mfa`` decorator checks that claim against a
   configurable max age (default 5 min).
3. On miss the decorator returns 403 with
   ``step_up_required=true`` and the step-up endpoint URL, prompting
   the client to call ``POST /api/auth/mfa/step-up``.
4. Step-up verifies the user's TOTP and returns a new access token
   with a fresh ``mfa_verified_at`` claim. The old access token is
   revoked to defend against replay.

Users without MFA enrolled hit 412 with
``mfa_enrollment_required=true`` — they must enroll before the
high-risk action can be attempted.
"""
from __future__ import annotations

from functools import wraps
from typing import Callable

from flask import jsonify, request
from flask_jwt_extended import get_jwt, verify_jwt_in_request

DEFAULT_MAX_AGE = 300  # seconds


def require_recent_mfa(max_age_seconds: int = DEFAULT_MAX_AGE) -> Callable:
    """Return a decorator enforcing a fresh MFA assertion."""

    def _decorator(func: Callable) -> Callable:
        @wraps(func)
        def _wrapper(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt() or {}
            from app.extensions import db
            from app.models.user import User
            from app.services import mfa as mfa_svc

            identity = claims.get("sub")
            if identity is None:
                return (
                    jsonify(error="authentication_required"),
                    401,
                )
            user = db.session.get(User, int(identity))
            if user is None or not user.is_active:
                return (
                    jsonify(error="authentication_required"),
                    401,
                )
            if not mfa_svc.is_enrolled(user):
                return (
                    jsonify(
                        error="mfa_enrollment_required",
                        mfa_enrollment_required=True,
                        enrollment_url="/api/auth/mfa/enroll",
                    ),
                    412,
                )
            # ``mfa_verified_at`` is seconds since the epoch; the
            # ``iat`` claim is the access-token issue time. We compare
            # against the current time to allow legitimate drift.
            import time

            mfa_at = claims.get("mfa_verified_at")
            now = int(time.time())
            if not isinstance(mfa_at, int) or now - mfa_at > max_age_seconds:
                return (
                    jsonify(
                        error="step_up_required",
                        step_up_required=True,
                        step_up_url="/api/auth/mfa/step-up",
                        max_age_seconds=max_age_seconds,
                    ),
                    403,
                )
            return func(*args, **kwargs)

        return _wrapper

    return _decorator
