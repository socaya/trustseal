"""Platform-admin user directory.

The interim API policy checks platform-admin privileges before these routes.
User deletion is a deactivation to preserve audit and document attribution.
"""
from flask import abort, jsonify, request
from sqlalchemy.exc import IntegrityError

from .. import users_bp
from app.extensions import db
from app.models.user import User
from app.models.organization import Organization

EDITABLE = {"first_name", "last_name", "phone", "is_active"}


def _payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="JSON object required")
    return data


def _serialize(user):
    return {
        "id": user.id, "username": user.username, "email": user.email,
        "first_name": user.first_name, "last_name": user.last_name,
        "phone": user.phone, "is_active": bool(user.is_active),
        "organization_id": user.organization_id,
    }


@users_bp.route("/api/users", methods=["GET"])
def list_users():
    page = request.args.get("page", 1, type=int)
    if page < 1 or page > 100000:
        abort(400, description="Invalid page")
    items = User.query.order_by(User.id.asc()).offset((page - 1) * 100).limit(100).all()
    return jsonify([_serialize(item) for item in items])


@users_bp.route("/api/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    return jsonify(_serialize(User.query.get_or_404(user_id)))


@users_bp.route("/api/users", methods=["POST"])
def create_user():
    data = _payload()
    required = ("username", "email", "password", "organization_id")
    if any(key not in data for key in required):
        abort(400, description="Username, email, password and organisation are required")
    if set(data) - {"username", "email", "password", "organization_id", "first_name", "last_name", "phone"}:
        abort(400, description="Unsupported fields")
    username, email, password = data["username"], data["email"], data["password"]
    if (not isinstance(username, str) or not 1 <= len(username.strip()) <= 64
            or not isinstance(email, str) or "@" not in email or len(email) > 120
            or not isinstance(password, str) or not 12 <= len(password) <= 1024):
        abort(400, description="Invalid account details")
    org_id = data["organization_id"]
    if type(org_id) is not int:
        abort(400, description="Invalid organisation")
    organisation = db.session.get(Organization, org_id)
    if organisation is None or not organisation.is_active:
        abort(400, description="Active organisation required")
    user = User(
        username=username.strip(), email=email.strip().lower(),
        first_name=data.get("first_name"), last_name=data.get("last_name"),
        phone=data.get("phone"), organization_id=org_id, is_active=True,
    )
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        abort(409, description="Username or email already exists")
    return jsonify(_serialize(user)), 201


@users_bp.route("/api/users/<int:user_id>", methods=["PUT"])
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = _payload()
    if not data or set(data) - EDITABLE:
        abort(400, description="Only profile fields and active status may be changed")
    for field, value in data.items():
        if field == "is_active":
            if type(value) is not bool:
                abort(400, description="is_active must be boolean")
        elif value is not None and not isinstance(value, str):
            abort(400, description="Invalid profile value")
        setattr(user, field, value)
    db.session.commit()
    return jsonify(_serialize(user))


@users_bp.route("/api/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active = False
    db.session.commit()
    return jsonify(message="User deactivated"), 200
