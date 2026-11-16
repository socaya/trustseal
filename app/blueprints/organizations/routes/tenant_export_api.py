"""Tenant data export admin endpoint (K1).

``POST /api/organizations/<id>/export`` returns the signed
tenant-data bundle. Admin-only and tenant-scoped — an admin in
org A cannot export org B's records.
"""
from __future__ import annotations

from flask import Blueprint, abort, jsonify

from flask_jwt_extended import jwt_required

from app.extensions import db
from app.policies.api_access import is_admin
from app.services import tenant_export
from app.services.token_security import active_token_user

tenant_export_api = Blueprint(
    "tenant_export_api", __name__, url_prefix="/api/organizations"
)


@tenant_export_api.route("/<int:organization_id>/export", methods=["POST"])
@jwt_required()
def export_organization(organization_id: int):
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    if user.organization_id != organization_id:
        abort(404)
    if not is_admin(user.id):
        abort(403, description="admin_required")
    try:
        signed = tenant_export.export_tenant(organization_id)
    except tenant_export.TenantExportError as exc:
        db.session.rollback()
        abort(400, description=str(exc))
    return jsonify(
        bundle=signed.bundle,
        bundle_sha256=signed.bundle_sha256,
        signature_hex=signed.signature_hex,
        signing_key_fingerprint=signed.signing_key_fingerprint,
    )
