"""Authentication API with durable JWT revocation and refresh-family rotation."""
from datetime import datetime, timezone

from flask import abort, request, jsonify, Blueprint
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.revoked_token import RevokedToken
from app.models.user import User
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
    db.session.add(user)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="Email or username already exists"), 409
    access, refresh = issue_login_tokens(user.id)
    db.session.commit()
    return jsonify(
        message="Registration successful",
        access_token=access,
        refresh_token=refresh,
        user_id=user.id,
    ), 201


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
