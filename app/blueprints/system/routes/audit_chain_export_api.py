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


@audit_chain_export_api.route("/proof", methods=["GET"])
@jwt_required()
def proof():
    """Return an inclusion proof for one SecurityEvent (Phase AH1).

    Given ``?event_id=X``, returns:

    * ``event`` — the chained-hash row for event X (id, prev_hash,
      event_hash, canonical_payload_sha256, created_at).
    * ``slice`` — every subsequent event up to and including the
      nearest anchor's ``anchor_event_id``. An auditor replays the
      chained-hash rule over this slice from X forward and arrives
      at the anchor's ``chain_tip_hash`` byte-for-byte.
    * ``anchor`` — the signed :class:`AuditChainAnchor` (payload,
      algorithm, key id, signature, chain tip). The signature
      bootstraps trust: if the anchor's Ed25519 verification
      succeeds, the derived chain tip is attributable.

    Admin-only and strictly tenant-scoped.
    """
    from app.extensions import db
    from app.models.audit_chain_anchor import AuditChainAnchor
    from app.models.event_delivery import SecurityEvent
    from app.services import audit_chain

    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    if not is_admin(user.id):
        abort(403, description="admin_required")
    event_id = request.args.get("event_id", type=int)
    if event_id is None or event_id <= 0:
        abort(400, description="event_id_required")
    event = (
        SecurityEvent.query.filter_by(
            id=event_id, organization_id=user.organization_id
        )
        .first()
    )
    if event is None:
        abort(404, description="event_not_found")
    anchor = (
        AuditChainAnchor.query.filter(
            AuditChainAnchor.organization_id == user.organization_id,
            AuditChainAnchor.anchor_event_id >= event_id,
        )
        .order_by(AuditChainAnchor.anchor_event_id.asc())
        .first()
    )
    if anchor is None:
        abort(409, description="no_anchor_yet_for_event")
    slice_rows = (
        SecurityEvent.query.filter(
            SecurityEvent.organization_id == user.organization_id,
            SecurityEvent.id > event.id,
            SecurityEvent.id <= anchor.anchor_event_id,
        )
        .order_by(SecurityEvent.id.asc())
        .all()
    )

    def _row(ev):
        return {
            "id": ev.id,
            "prev_event_hash": ev.prev_event_hash,
            "event_hash": ev.event_hash,
            "canonical_payload_sha256": audit_chain.canonical_payload_hash(ev),
            "created_at": ev.created_at.isoformat(),
        }

    return jsonify(
        event=_row(event),
        slice=[_row(r) for r in slice_rows],
        anchor={
            "id": anchor.id,
            "anchor_event_id": anchor.anchor_event_id,
            "chain_tip_hash": anchor.chain_tip_hash,
            "payload": anchor.payload,
            "algorithm": anchor.algorithm,
            "key_id": anchor.key_id,
            "signature": anchor.signature,
            "created_at": anchor.created_at.isoformat(),
        },
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
