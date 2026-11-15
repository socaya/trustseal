"""Authentication API with durable JWT revocation and refresh-family rotation."""
from datetime import datetime, timezone

from flask import abort, request, jsonify, Blueprint, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.revoked_token import RevokedToken
from app.models.user import User
from app.services import email_verification, password_reset, sessions
from app.services.rate_limiting import consume as rate_consume
from app.services.refresh_tokens import (
    RefreshRejected,
    ReuseDetected,
    issue_login_tokens,
    revoke_all_for_user,
    rotate,
)
from app.services.token_security import active_token_user, revoke_token

auth_api = Blueprint("auth_api", __name__, url_prefix="/api/auth")


def _data():
    value = request.get_json(silent=True)
    return value if isinstance(value, dict) else {}


@auth_api.route("/register", methods=["POST"])
def register_api():
    data = _data()
    username = str(data.get("username") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    password = data.get("password")
    if not username or len(username) > 64 or not email or len(email) > 120 or "@" not in email:
        return jsonify(error="Valid username and email are required"), 400
    if not isinstance(password, str) or len(password) < 12 or len(password) > 1024:
        return jsonify(error="Password must contain at least 12 characters"), 400
    if User.query.filter((User.email == email) | (User.username == username)).first():
        return jsonify(error="Email or username already exists"), 409

    user = User(
        username=username,
        email=email,
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
        phone=data.get("phone"),
    )
    user.set_password(password)
    user.last_password_change_at = datetime.utcnow()
    db.session.add(user)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="Email or username already exists"), 409
    # Issue a verification email. Failures to deliver are logged but
    # do not fail registration — the user can request a resend.
    try:
        email_verification.issue(user, ip=_client_ip())
    except Exception:  # pragma: no cover
        current_app.logger.exception("email verification issuance failed")
        db.session.rollback()
        return jsonify(error="registration_failed"), 500
    access, refresh = issue_login_tokens(user.id)
    db.session.commit()
    return jsonify(
        message="Registration successful",
        access_token=access,
        refresh_token=refresh,
        user_id=user.id,
        email_verified=False,
    ), 201


def _client_ip() -> str | None:
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    return forwarded or request.remote_addr


@auth_api.route("/verify-email/<token>", methods=["POST"])
def verify_email_api(token: str):
    """Consume an email verification token and mark the user verified."""
    try:
        user = email_verification.consume(token)
    except email_verification.VerificationError as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 400
    db.session.commit()
    return jsonify(
        message="email_verified",
        user_id=user.id,
        email=user.email,
        email_verified=True,
    ), 200


@auth_api.route("/verify-email/resend", methods=["POST"])
@jwt_required()
def resend_verification_api():
    """Request a fresh verification email for the authenticated user."""
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    if user.email_verified:
        return jsonify(error="already_verified"), 400
    decision = rate_consume(
        bucket_key=f"email-verify-resend:{user.id}",
        max_hits=3,
        window_seconds=3600,
    )
    if not decision.allowed:
        return (
            jsonify(
                error="rate_limited",
                retry_after_seconds=decision.retry_after_seconds,
            ),
            429,
        )
    try:
        email_verification.resend(user, ip=_client_ip())
    except email_verification.VerificationError as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 400
    db.session.commit()
    return jsonify(message="verification_email_sent"), 200


@auth_api.route("/login", methods=["POST"])
def login_api():
    data = _data()
    identifier = data.get("identifier")
    password = data.get("password")
    if not isinstance(identifier, str) or not isinstance(password, str) or not identifier or not password:
        return jsonify(error="Missing credentials"), 400
    user = User.query.filter((User.email == identifier.strip().lower()) |
                             (User.username == identifier.strip())).first()
    if user is None or not user.is_active or not user.check_password(password):
        return jsonify(error="Invalid credentials"), 401
    access, refresh = issue_login_tokens(user.id)
    db.session.commit()
    return jsonify(
        access_token=access,
        refresh_token=refresh,
        user=user.to_dict(),
    ), 200


@auth_api.route("/logout", methods=["POST"])
@jwt_required(verify_type=False)
def logout_api():
    revoke_token(get_jwt())
    db.session.commit()
    return jsonify(message="Logout successful", redirect="/auth/login"), 200


@auth_api.route("/me", methods=["GET"])
@jwt_required()
def me_api():
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None or not user.is_active:
        return jsonify(error="User not found"), 404
    return jsonify(
        id=user.id, username=user.username, email=user.email,
        first_name=user.first_name, last_name=user.last_name, phone=user.phone,
    ), 200


@auth_api.route("/change-password", methods=["POST"])
@jwt_required()
def change_password():
    """Change the caller's own password.

    Verifies the current password, enforces the registration strength
    rules, revokes every outstanding refresh family (so stolen
    pre-change tokens cannot be redeemed), revokes the current access
    token, and returns a freshly issued access + refresh pair.
    """
    actor = active_token_user()
    if actor is None or not actor.is_active:
        abort(401)
    data = _data()
    if set(data) != {"current_password", "new_password"}:
        abort(400, description="current_password_and_new_password_required")
    current = data["current_password"]
    new_password = data["new_password"]
    if not isinstance(current, str) or not isinstance(new_password, str):
        abort(400, description="credentials_must_be_strings")
    if not actor.check_password(current):
        abort(401, description="current_password_incorrect")
    if not 12 <= len(new_password) <= 1024:
        abort(400, description="new_password_strength")
    if new_password == current:
        abort(400, description="new_password_must_differ")
    actor.set_password(new_password)
    revoke_all_for_user(actor.id, reason="password_changed")
    access_payload = get_jwt()
    if (
        access_payload.get("jti")
        and db.session.get(RevokedToken, access_payload["jti"]) is None
    ):
        db.session.add(
            RevokedToken(
                jti=access_payload["jti"],
                user_id=actor.id,
                expires_at=datetime.fromtimestamp(
                    access_payload["exp"], tz=timezone.utc
                ),
            )
        )
    access, refresh = issue_login_tokens(actor.id)
    db.session.commit()
    return jsonify(
        message="Password updated",
        access_token=access,
        refresh_token=refresh,
    ), 200


@auth_api.route("/sessions", methods=["GET"])
@jwt_required()
def list_sessions_api():
    """List the caller's own active + revoked sessions."""
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    return jsonify(sessions=sessions.list_sessions(user.id)), 200


@auth_api.route("/sessions/<int:session_id>", methods=["DELETE"])
@jwt_required()
def revoke_session_api(session_id: int):
    """Revoke a specific session owned by the caller."""
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    try:
        sessions.revoke(user.id, session_id, reason="user")
    except LookupError:
        db.session.rollback()
        return jsonify(error="session_not_found"), 404
    db.session.commit()
    return jsonify(message="session_revoked", session_id=session_id), 200


@auth_api.route("/sessions/others", methods=["DELETE"])
@jwt_required()
def revoke_other_sessions_api():
    """Sign out every session except the caller's current one."""
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    claims = get_jwt()
    keep_family = claims.get("fam")
    if keep_family is None:
        # No family claim on this access token (older session); treat
        # it as if nothing is being kept — the caller will be logged
        # out of every session.
        keep_family = -1
    revoked = sessions.revoke_others(user.id, int(keep_family), reason="user")
    db.session.commit()
    return jsonify(message="other_sessions_revoked", revoked=revoked), 200


@auth_api.route("/password-reset/request", methods=["POST"])
def password_reset_request_api():
    """Begin a password reset flow.

    Always returns 202 to prevent email enumeration. Rate-limited by
    source IP so an attacker cannot spam reset emails.
    """
    data = _data()
    email = str(data.get("email") or "").strip().lower()
    if not email or "@" not in email or len(email) > 120:
        # Still return 202 so callers cannot infer malformed-vs-missing.
        return jsonify(message="password_reset_email_queued"), 202
    ip = _client_ip() or "unknown"
    decision = rate_consume(
        bucket_key=f"password-reset-request:{ip}",
        max_hits=5,
        window_seconds=3600,
    )
    if not decision.allowed:
        return (
            jsonify(
                error="rate_limited",
                retry_after_seconds=decision.retry_after_seconds,
            ),
            429,
        )
    try:
        password_reset.request_reset(email, ip=_client_ip())
    except Exception:  # pragma: no cover
        current_app.logger.exception("password reset request failed")
        db.session.rollback()
        return jsonify(error="request_failed"), 500
    db.session.commit()
    return jsonify(message="password_reset_email_queued"), 202


@auth_api.route("/password-reset/<token>/consume", methods=["POST"])
def password_reset_consume_api(token: str):
    """Finish a password reset by consuming a token and setting a new password."""
    data = _data()
    new_password = data.get("new_password")
    try:
        user = password_reset.consume(token, new_password=new_password)
    except password_reset.ResetError as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 400
    access, refresh = issue_login_tokens(user.id)
    db.session.commit()
    return jsonify(
        message="password_updated",
        access_token=access,
        refresh_token=refresh,
    ), 200


@auth_api.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh_token():
    try:
        access, refresh = rotate(get_jwt())
    except ReuseDetected:
        db.session.commit()
        return (
            jsonify(
                error="Refresh token reuse detected; session terminated.",
                type="https://trustseal.dev/problems/refresh-token-reuse",
            ),
            401,
        )
    except RefreshRejected as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 401
    db.session.commit()
    return jsonify(access_token=access, refresh_token=refresh), 200
