"""Break-glass admin endpoints (K3).

* ``POST   /api/_internal/break-glass`` — issue a grant.
* ``DELETE /api/_internal/break-glass/<id>`` — revoke a grant.

Both require admin. Separation-of-duties forbids self-grant
(enforced inside the service).
"""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.policies.api_access import is_admin
from app.services import break_glass
from app.services.token_security import active_token_user

break_glass_api = Blueprint(
    "break_glass_api", __name__, url_prefix="/api/_internal"
)


@break_glass_api.route("/break-glass", methods=["POST"])
@jwt_required()
def issue_grant():
    actor = active_token_user()
    if actor is None or not actor.is_active:
        abort(401)
    if not is_admin(actor.id):
        abort(403, description="admin_required")
    data = request.get_json(silent=True) or {}
    operator_id = data.get("operator_id")
    scope = data.get("scope")
    reason = data.get("reason")
    if not isinstance(operator_id, int):
        abort(400, description="operator_id_required")
    try:
        issue = break_glass.grant(
            operator_id=operator_id,
            granted_by_id=actor.id,
            scope=str(scope or ""),
            reason=str(reason or ""),
            ttl_minutes=data.get("ttl_minutes"),
            organization_id=data.get("organization_id"),
        )
    except break_glass.BreakGlassError as exc:
        db.session.rollback()
        abort(400, description=str(exc))
    db.session.commit()
    return jsonify(
        grant_id=issue.grant_id,
        access_token=issue.access_token,
        expires_at=issue.expires_at.isoformat(),
    )


@break_glass_api.route("/break-glass/<int:grant_id>", methods=["DELETE"])
@jwt_required()
def revoke_grant(grant_id: int):
    actor = active_token_user()
    if actor is None or not actor.is_active:
        abort(401)
    if not is_admin(actor.id):
        abort(403, description="admin_required")
    data = request.get_json(silent=True) or {}
    try:
        row = break_glass.revoke(
            grant_id, revoked_by_id=actor.id, reason=data.get("reason")
        )
    except break_glass.BreakGlassError as exc:
        db.session.rollback()
        abort(404, description=str(exc))
    db.session.commit()
    return jsonify(
        grant_id=row.id,
        revoked_at=row.revoked_at.isoformat(),
    )
