"""Signed audit-chain slice export (M3)."""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, request
from flask_jwt_extended import jwt_required

from app.policies.api_access import is_admin
from app.services import audit_chain_export
from app.services.token_security import active_token_user

audit_chain_export_api = Blueprint(
    "audit_chain_export_api", __name__, url_prefix="/api/_internal/audit"
)


@audit_chain_export_api.route("/export", methods=["GET"])
@jwt_required()
def export():
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    if not is_admin(user.id):
        abort(403, description="admin_required")
    from_id = request.args.get("from_id", type=int)
    to_id = request.args.get("to_id", type=int)
    max_rows = request.args.get("max_rows", default=10_000, type=int)
    # Admins must scope to their own tenant unless they are a
    # "superadmin" — this policy follows the same pattern as the
    # tenant_export endpoint.
    try:
        signed = audit_chain_export.export_slice(
            organization_id=user.organization_id,
            from_id=from_id,
            to_id=to_id,
            max_rows=max_rows,
        )
    except audit_chain_export.AuditChainExportError as exc:
        abort(400, description=str(exc))
    return jsonify(
        bundle=signed.bundle,
        bundle_sha256=signed.bundle_sha256,
        signature_hex=signed.signature_hex,
        signing_key_fingerprint=signed.signing_key_fingerprint,
    )
