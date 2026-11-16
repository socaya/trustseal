"""Operator-controlled step-up MFA enforcement for high-risk routes.

The Phase A4 ``@require_recent_mfa`` decorator is a mechanism — a
callable the application can apply to any route. Phase I1 wires it
into the actual high-risk routes (envelope prepare, stamp approve,
template publish, clause approve, admin role grant) behind a single
operator-controlled toggle: ``STEP_UP_MFA_REQUIRED``.

Rollout strategy:

* The config defaults to ``False`` so existing deployments and tests
  keep working.
* Operators flip ``STEP_UP_MFA_REQUIRED=true`` when they are ready
  to enforce four-eyes TOTP on privileged actions.
* The enforcement is inline — routes call :func:`enforce` and the
  helper either passes (disabled or recent MFA present) or aborts
  with 403 ``step_up_required``.

The reason this is not just the decorator is that routes already run
through their own authenticator (JWT + api_access policy) and
sometimes catch other exceptions; a direct inline call plays more
nicely with those existing guards than a pre-view decorator wrapper.
"""
from __future__ import annotations

import time
from typing import Optional

from flask import abort, current_app, jsonify
from flask_jwt_extended import get_jwt

from app.extensions import db
from app.models.user import User
from app.services import mfa as mfa_svc

DEFAULT_MAX_AGE = 300


def enabled() -> bool:
    """Return True when the operator has turned step-up enforcement on."""
    return bool(current_app.config.get("STEP_UP_MFA_REQUIRED", False))


def enforce(max_age_seconds: int = DEFAULT_MAX_AGE) -> None:
    """Abort the request when step-up is required but missing.

    Safe to call on routes that have already run ``@jwt_required``.
    No-op when ``STEP_UP_MFA_REQUIRED`` is False.
    """
    if not enabled():
        return
    claims = get_jwt() or {}
    identity = claims.get("sub")
    if identity is None:
        abort(401)
    user = db.session.get(User, int(identity))
    if user is None or not user.is_active:
        abort(401)
    if not mfa_svc.is_enrolled(user):
        resp = jsonify(
            error="mfa_enrollment_required",
            mfa_enrollment_required=True,
            enrollment_url="/api/auth/mfa/enroll",
        )
        resp.status_code = 412
        abort(resp)
    mfa_at = claims.get("mfa_verified_at")
    now = int(time.time())
    if not isinstance(mfa_at, int) or now - mfa_at > max_age_seconds:
        resp = jsonify(
            error="step_up_required",
            step_up_required=True,
            step_up_url="/api/auth/mfa/step-up",
            max_age_seconds=max_age_seconds,
        )
        resp.status_code = 403
        abort(resp)
