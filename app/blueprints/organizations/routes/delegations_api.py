"""Delegation management API.

* ``POST   /api/delegations`` — grant a delegation. The caller
  must be either the delegator themselves or an admin.
* ``GET    /api/delegations/outgoing`` — delegations the caller has
  granted.
* ``GET    /api/delegations/incoming`` — delegations the caller has
  received (active + historical).
* ``DELETE /api/delegations/<id>`` — revoke. The caller must be the
  delegator or an admin.

Grants must specify a scope and an expiry; windows are validated in
the service layer.
"""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, abort, jsonify, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.delegation import Delegation
from app.policies.api_access import is_admin
from app.services import delegations as delegation_service
from app.services.token_security import active_token_user

delegations_api = Blueprint(
    "delegations_api", __name__, url_prefix="/api/delegations"
)


def _actor():
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    return user


def _to_dict(row: Delegation) -> dict:
    return {
        "id": row.id,
        "delegator_id": row.delegator_id,
        "delegate_id": row.delegate_id,
        "scope": row.scope,
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "reason": row.reason,
        "starts_at": row.starts_at.isoformat(),
        "expires_at": row.expires_at.isoformat(),
        "granted_at": row.granted_at.isoformat(),
        "granted_by_id": row.granted_by_id,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "revoked_by_id": row.revoked_by_id,
        "revoke_reason": row.revoke_reason,
        "active": row.revoked_at is None,
    }


def _parse_iso(value, field):
    if not isinstance(value, str):
        abort(400, description=f"{field}_required")
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        abort(400, description=f"{field}_invalid_iso")


@delegations_api.route("", methods=["POST"])
@jwt_required()
def grant():
    actor = _actor()
    data = request.get_json(silent=True) or {}
    delegator_id = data.get("delegator_id", actor.id)
    delegate_id = data.get("delegate_id")
    if not isinstance(delegate_id, int):
        abort(400, description="delegate_id_required")
    if delegator_id != actor.id and not is_admin(actor.id):
        abort(403, description="cannot_grant_on_behalf")
    try:
        row = delegation_service.grant(
            delegator_id=int(delegator_id),
            delegate_id=int(delegate_id),
            scope=str(data.get("scope", "")),
            starts_at=_parse_iso(data.get("starts_at"), "starts_at"),
            expires_at=_parse_iso(data.get("expires_at"), "expires_at"),
            granted_by_id=actor.id,
            organization_id=actor.organization_id,
            resource_type=data.get("resource_type"),
            resource_id=data.get("resource_id"),
            reason=data.get("reason"),
        )
    except delegation_service.DelegationError as exc:
        db.session.rollback()
        abort(400, description=str(exc))
    db.session.commit()
    return jsonify(_to_dict(row)), 201


@delegations_api.route("/outgoing", methods=["GET"])
@jwt_required()
def outgoing():
    actor = _actor()
    rows = (
        Delegation.query.filter_by(delegator_id=actor.id)
        .order_by(Delegation.granted_at.desc())
        .all()
    )
    return jsonify(delegations=[_to_dict(r) for r in rows]), 200


@delegations_api.route("/incoming", methods=["GET"])
@jwt_required()
def incoming():
    actor = _actor()
    rows = (
        Delegation.query.filter_by(delegate_id=actor.id)
        .order_by(Delegation.granted_at.desc())
        .all()
    )
    return jsonify(delegations=[_to_dict(r) for r in rows]), 200


@delegations_api.route("/<int:delegation_id>", methods=["DELETE"])
@jwt_required()
def revoke(delegation_id):
    actor = _actor()
    row = db.session.get(Delegation, delegation_id)
    if row is None or row.organization_id != actor.organization_id:
        abort(404)
    if row.delegator_id != actor.id and not is_admin(actor.id):
        abort(403, description="only_delegator_or_admin_may_revoke")
    data = request.get_json(silent=True) or {}
    try:
        row = delegation_service.revoke(
            delegation_id,
            revoked_by_id=actor.id,
            reason=data.get("reason"),
        )
    except delegation_service.DelegationError as exc:
        db.session.rollback()
        abort(404, description=str(exc))
    db.session.commit()
    return jsonify(_to_dict(row)), 200
