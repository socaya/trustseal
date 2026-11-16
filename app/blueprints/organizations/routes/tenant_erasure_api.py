"""Tenant user erasure admin endpoint (K2).

``POST /api/organizations/<org>/users/<user>/erase`` triggers the
GDPR Article 17 erasure for a single user in the admin's tenant.
Admin-only, cross-tenant 404, and refuses self-erasure.
"""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.user import User
from app.policies.api_access import is_admin
from app.services import tenant_erasure
from app.services.token_security import active_token_user

tenant_erasure_api = Blueprint(
    "tenant_erasure_api",
    __name__,
    url_prefix="/api/organizations",
)


@tenant_erasure_api.route(
    "/<int:organization_id>/users/<int:user_id>/erase", methods=["POST"]
)
@jwt_required()
def erase_user(organization_id: int, user_id: int):
    actor = active_token_user()
    if actor is None or not actor.is_active:
        abort(401)
    if actor.organization_id != organization_id:
        abort(404)
    if not is_admin(actor.id):
        abort(403, description="admin_required")
    target = db.session.get(User, user_id)
    if target is None or target.organization_id != organization_id:
        abort(404)
    data = request.get_json(silent=True) or {}
    try:
        outcome = tenant_erasure.erase_user(
            user_id=user_id,
            requested_by_id=actor.id,
            reason=data.get("reason"),
        )
    except tenant_erasure.ErasureError as exc:
        db.session.rollback()
        abort(409, description=str(exc))
    db.session.commit()
    return jsonify(
        user_id=outcome.user_id,
        pseudonym=outcome.pseudonym,
        erased_at=outcome.erased_at.isoformat(),
    )
