"""Authentication API with durable JWT revocation and basic input validation."""
from flask import request, jsonify, Blueprint
from flask_jwt_extended import (
    create_access_token, create_refresh_token, jwt_required,
    get_jwt_identity, get_jwt,
)
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.user import User
from app.services.token_security import revoke_token

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
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="Email or username already exists"), 409
    return jsonify(
        message="Registration successful",
        access_token=create_access_token(identity=str(user.id)),
        refresh_token=create_refresh_token(identity=str(user.id)),
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
    return jsonify(
        access_token=create_access_token(identity=str(user.id)),
        refresh_token=create_refresh_token(identity=str(user.id)),
        user=user.to_dict(),
    ), 200


@auth_api.route("/logout", methods=["POST"])
@jwt_required(verify_type=False)
def logout_api():
    revoke_token(get_jwt())
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


@auth_api.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh_token():
    return jsonify(access_token=create_access_token(identity=get_jwt_identity())), 200
