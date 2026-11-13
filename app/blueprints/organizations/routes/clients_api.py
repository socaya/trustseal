"""Organisation-scoped client directory.

Client IDs must resolve within the caller's organisation. Organisation IDs
are assigned server-side, never trusted from a request body.
"""
from flask import abort, jsonify, request
from flask_jwt_extended import jwt_required

from .. import organizations_bp
from app.extensions import db
from app.models.organization import Client
from app.services.token_security import active_token_user

WRITABLE = {"name", "email", "phone", "address", "tax_id", "notes"}


def _actor():
    user = active_token_user()
    if user is None or not user.is_active or user.organization_id is None:
        abort(403)
    return user


def _payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) - WRITABLE:
        abort(400, description="Invalid client payload")
    if "name" in data and (
        not isinstance(data["name"], str) or not 1 <= len(data["name"].strip()) <= 120
    ):
        abort(400, description="Invalid client name")
    for key in WRITABLE - {"name"}:
        if key in data and data[key] is not None and not isinstance(data[key], str):
            abort(400, description="Invalid client field")
    return data


def _owned(client_id, user):
    item = Client.query.filter_by(id=client_id, organization_id=user.organization_id).first()
    if item is None:
        abort(404)
    return item


def _serialize(item):
    return {"id": item.id, "name": item.name, "email": item.email,
            "phone": item.phone, "organization_id": item.organization_id,
            "is_active": item.is_active}


@organizations_bp.route("/api/clients", methods=["GET"])
@jwt_required()
def list_clients():
    user = _actor()
    items = Client.query.filter_by(organization_id=user.organization_id).limit(100).all()
    return jsonify([_serialize(item) for item in items])


@organizations_bp.route("/api/clients", methods=["POST"])
@jwt_required()
def create_client():
    user = _actor()
    data = _payload()
    if "name" not in data:
        abort(400, description="Client name required")
    item = Client(organization_id=user.organization_id, **data)
    db.session.add(item)
    db.session.commit()
    return jsonify(_serialize(item)), 201


@organizations_bp.route("/api/clients/<int:client_id>", methods=["PUT"])
@jwt_required()
def update_client(client_id):
    item = _owned(client_id, _actor())
    data = _payload()
    for key, value in data.items():
        setattr(item, key, value)
    db.session.commit()
    return jsonify(_serialize(item))


@organizations_bp.route("/api/clients/<int:client_id>", methods=["DELETE"])
@jwt_required()
def delete_client(client_id):
    item = _owned(client_id, _actor())
    # Do not cascade-delete historic document associations.
    item.is_active = False
    db.session.commit()
    return jsonify(message="Client deactivated"), 200
