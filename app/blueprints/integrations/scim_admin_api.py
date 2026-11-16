"""SCIM service-account lifecycle endpoints (Phase L1).

Separate blueprint from the SCIM protocol surface (which runs under
``/scim/v2``). These admin endpoints let the tenant's human admin
create, list, rotate, and revoke bearer tokens used by provisioning
integrations.
"""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.policies.api_access import is_admin
from app.services import scim as scim_service
from app.services.token_security import active_token_user

scim_admin_api = Blueprint(
    "scim_admin_api", __name__, url_prefix="/api/scim/service-accounts"
)


def _admin():
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    if not is_admin(user.id):
        abort(403, description="admin_required")
    if user.organization_id is None:
        abort(403, description="organization_required")
    return user


def _dict(row) -> dict:
    return {
        "id": row.id,
        "display_name": row.display_name,
        "active": row.active,
        "created_at": row.created_at.isoformat(),
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "revoke_reason": row.revoke_reason,
        "rotated_from_id": row.rotated_from_id,
    }


@scim_admin_api.route("", methods=["POST"])
@jwt_required()
def create_account():
    user = _admin()
    data = request.get_json(silent=True) or {}
    try:
        row, token = scim_service.mint_token(
            tenant_id=user.organization_id,
            created_by_id=user.id,
            display_name=str(data.get("display_name", "")),
            expires_in_days=data.get("expires_in_days"),
        )
    except scim_service.ScimError as exc:
        db.session.rollback()
        abort(400, description=str(exc))
    db.session.commit()
    payload = _dict(row)
    payload["token"] = token  # returned once, never again
    return jsonify(payload), 201


@scim_admin_api.route("", methods=["GET"])
@jwt_required()
def list_accounts():
    user = _admin()
    rows = scim_service.list_accounts(user.organization_id)
    return jsonify(accounts=[_dict(r) for r in rows])


@scim_admin_api.route("/<int:account_id>/rotate", methods=["POST"])
@jwt_required()
def rotate_account(account_id: int):
    user = _admin()
    data = request.get_json(silent=True) or {}
    try:
        row, token = scim_service.rotate_token(
            account_id,
            tenant_id=user.organization_id,
            rotated_by_id=user.id,
            expires_in_days=data.get("expires_in_days"),
        )
    except scim_service.ScimError as exc:
        db.session.rollback()
        status = exc.status if 400 <= exc.status < 600 else 400
        abort(status, description=str(exc))
    db.session.commit()
    payload = _dict(row)
    payload["token"] = token
    return jsonify(payload), 201


@scim_admin_api.route("/<int:account_id>", methods=["DELETE"])
@jwt_required()
def revoke_account(account_id: int):
    user = _admin()
    data = request.get_json(silent=True) or {}
    try:
        row = scim_service.revoke_token(
            account_id,
            tenant_id=user.organization_id,
            revoked_by_id=user.id,
            reason=data.get("reason"),
        )
    except scim_service.ScimError as exc:
        db.session.rollback()
        status = exc.status if 400 <= exc.status < 600 else 400
        abort(status, description=str(exc))
    db.session.commit()
    return jsonify(_dict(row))
