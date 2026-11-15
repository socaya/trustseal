"""MFA enrollment and verification API.

Three routes:

* ``POST /api/auth/mfa/enroll`` — start or reset an enrollment. Returns
  the TOTP secret and QR provisioning URI once.
* ``POST /api/auth/mfa/confirm`` — confirm the first TOTP code and
  receive the recovery codes once.
* ``POST /api/auth/mfa/disable`` — disable the credential (requires a
  current TOTP or recovery code so a stolen access token cannot
  silently turn off MFA).
* ``GET  /api/auth/mfa/status`` — a boolean + remaining recovery code
  count. Safe to expose because it reveals nothing about the secret.

Every mutation requires an authenticated caller and the active SECRET_KEY
to be strong enough to derive the encryption key.
"""
from __future__ import annotations

from flask import Blueprint, abort, current_app, jsonify, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.user import User
from app.services import mfa as mfa_service
from app.services.idempotency import idempotent
from app.services.token_security import active_token_user

mfa_api = Blueprint("mfa_api", __name__, url_prefix="/api/auth/mfa")


def _require_user() -> User:
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    return user


@mfa_api.route("/status", methods=["GET"])
@jwt_required()
def status():
    user = _require_user()
    return jsonify(
        {
            "enrolled": mfa_service.is_enrolled(user),
            "unused_recovery_codes": mfa_service.unused_recovery_code_count(user),
        }
    )


@mfa_api.route("/enroll", methods=["POST"])
@jwt_required()
@idempotent("mfa.enroll")
def enroll():
    user = _require_user()
    if mfa_service.is_enrolled(user):
        abort(409, description="mfa_already_enrolled")
    try:
        result = mfa_service.begin_enrollment(
            user, app_secret=current_app.config["SECRET_KEY"]
        )
    except mfa_service.MfaError as exc:
        abort(400, description=str(exc))
    db.session.commit()
    return (
        jsonify(
            {
                "secret": result.secret,
                "otpauth_uri": result.otpauth_uri,
                "issuer": result.issuer,
                "secret_disclosure_once": True,
            }
        ),
        201,
    )


@mfa_api.route("/confirm", methods=["POST"])
@jwt_required()
@idempotent("mfa.confirm")
def confirm():
    user = _require_user()
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"code"}:
        abort(400, description="code_required")
    try:
        result = mfa_service.confirm_enrollment(
            user,
            data["code"],
            app_secret=current_app.config["SECRET_KEY"],
        )
    except mfa_service.MfaError as exc:
        abort(400, description=str(exc))
    db.session.commit()
    return jsonify(
        {
            "recovery_codes": result.recovery_codes,
            "recovery_disclosure_once": True,
        }
    )


@mfa_api.route("/disable", methods=["POST"])
@jwt_required()
@idempotent("mfa.disable")
def disable():
    user = _require_user()
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"code"}:
        abort(400, description="code_required")
    if not mfa_service.is_enrolled(user):
        abort(409, description="mfa_not_enrolled")
    try:
        mfa_service.verify(
            user, data["code"], app_secret=current_app.config["SECRET_KEY"]
        )
        mfa_service.disable(user)
    except mfa_service.MfaError as exc:
        abort(400, description=str(exc))
    db.session.commit()
    return jsonify({"enrolled": False})
