"""Tenant-scoped organisation API.

Legal verification status is never client-writable. Organisation provisioning
remains platform-admin only under the central API policy.
"""
from flask import abort, jsonify, request
from flask_jwt_extended import jwt_required

from .. import organizations_bp
from app.extensions import db
from app.models.organization import Organization
from app.services.token_security import active_token_user
from app.policies.api_access import is_admin

WRITABLE = {"name", "legal_name", "registration_number", "email", "phone",
            "website", "country", "type", "address"}


def _actor():
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    return user


def _payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="JSON object required")
    if set(data) - WRITABLE:
        abort(400, description="Unsupported or protected organisation fields")
    if "name" in data and (
        not isinstance(data["name"], str) or not 1 <= len(data["name"].strip()) <= 120
    ):
        abort(400, description="Invalid organisation name")
    if "type" in data and data["type"] not in ("individual", "company"):
        abort(400, description="Invalid organisation type")
    return data


def _visible_organisation(org_id, user):
    org = db.session.get(Organization, org_id)
    if org is None or (not is_admin(user.id) and user.organization_id != org_id):
        abort(404)
    return org


def _serialize(org):
    return {
        "id": org.id, "name": org.name, "legal_name": org.legal_name,
        "email": org.email, "country": org.country, "type": org.type,
        "website": org.website, "is_verified": bool(org.is_verified),
        "is_active": bool(org.is_active),
    }


@organizations_bp.route("/api/organizations", methods=["GET"], endpoint="all_organizations")
@jwt_required()
def all_organizations():
    user = _actor()
    query = Organization.query
    if not is_admin(user.id):
        query = query.filter(Organization.id == user.organization_id)
    return jsonify([_serialize(org) for org in query.limit(100).all()])


@organizations_bp.route("/api/organizations/<int:org_id>", methods=["GET"])
@jwt_required()
def get_organization(org_id):
    return jsonify(_serialize(_visible_organisation(org_id, _actor())))


@organizations_bp.route("/api/organizations", methods=["POST"])
@jwt_required()
def create_organization():
    _actor()
    data = _payload()
    if "name" not in data:
        abort(400, description="Organisation name is required")
    org = Organization(**data)
    org.is_verified = False
    db.session.add(org)
    db.session.commit()
    return jsonify(_serialize(org)), 201


@organizations_bp.route("/api/organizations/<int:org_id>", methods=["PUT"])
@jwt_required()
def update_organization(org_id):
    user = _actor()
    org = _visible_organisation(org_id, user)
    data = _payload()
    for key, value in data.items():
        setattr(org, key, value)
    db.session.commit()
    return jsonify(_serialize(org))


@organizations_bp.route("/api/organizations/<int:org_id>", methods=["DELETE"])
@jwt_required()
def delete_organization(org_id):
    user = _actor()
    org = _visible_organisation(org_id, user)
    # Preserve documents and historical evidence; disable rather than cascade-delete.
    org.is_active = False
    db.session.commit()
    return jsonify(message="Organisation deactivated"), 200
