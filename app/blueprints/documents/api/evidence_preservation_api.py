"""Authenticated, tenant-scoped legal hold and retention management.

No deletion, retention-shortening, or public document enumeration endpoint.
Admins can place holds; only a different admin may release them.
"""
import re
from datetime import datetime, timedelta

from flask import Blueprint, abort, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.evidence_preservation import EvidenceRetention, EvidenceLegalHold, EvidenceCheckpoint
from app.services.evidence_preservation import artifact_for, protection_status
from app.services.event_delivery import enqueue
from app.services.token_security import active_token_user
from app.policies.api_access import is_admin

evidence_preservation_api = Blueprint(
    "evidence_preservation_api", __name__, url_prefix="/api/evidence-preservation"
)


def _admin():
    actor = active_token_user()
    if actor is None or not actor.is_active or actor.organization_id is None:
        abort(401)
    if not is_admin(actor.id):
        abort(403)
    return actor


def _retention(retention_id, actor, lock=False):
    query = EvidenceRetention.query.filter_by(
        id=retention_id, organization_id=actor.organization_id
    )
    result = (query.with_for_update() if lock else query).first()
    if result is None:
        abort(404)
    return result


def _hold_count(retention_id):
    return EvidenceLegalHold.query.filter_by(
        retention_id=retention_id, released_at=None
    ).count()


@evidence_preservation_api.route("/retentions", methods=["POST"])
@jwt_required()
def register_retention():
    actor = _admin()
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"artifact_type", "artifact_id", "retention_days"}:
        abort(400)
    kind, artifact_id, days = data["artifact_type"], data["artifact_id"], data["retention_days"]
    if (kind not in ("finalized_pdf", "stamped_pdf")
            or type(artifact_id) is not int or type(days) is not int
            or not 365 <= days <= 36500):
        abort(400, description="Retention must be between one and 100 years")
    try:
        artifact = artifact_for(kind, artifact_id, actor.organization_id)
    except ValueError:
        abort(404)
    existing = EvidenceRetention.query.filter_by(
        artifact_type=kind, artifact_id=artifact_id
    ).first()
    if existing is not None:
        abort(409, description="Retention cannot be overwritten or shortened")
    retention = EvidenceRetention(
        organization_id=actor.organization_id, artifact_type=kind,
        artifact_id=artifact_id, artifact_sha256=artifact.output_sha256,
        retain_until=datetime.utcnow() + timedelta(days=days),
        created_by_id=actor.id,
    )
    db.session.add(retention)
    try:
        db.session.flush()
        enqueue(
            event_type="evidence.retention.registered",
            aggregate_type="evidence_retention", aggregate_id=retention.id,
            organization_id=actor.organization_id, actor_id=actor.id,
            action="evidence.retention.registered",
            idempotency_key="evidence-retention:%s" % retention.id,
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        abort(409, description="Retention record already exists")
    return jsonify({
        "id": retention.id, "artifact_type": kind, "artifact_id": artifact_id,
        **protection_status(retention, 0),
    }), 201


@evidence_preservation_api.route("/retentions/<int:retention_id>", methods=["GET"])
@jwt_required()
def get_retention(retention_id):
    actor = _admin()
    item = _retention(retention_id, actor)
    return jsonify({
        "id": item.id, "artifact_type": item.artifact_type,
        "artifact_id": item.artifact_id, "artifact_sha256": item.artifact_sha256,
        **protection_status(item, _hold_count(item.id)),
    })


@evidence_preservation_api.route("/retentions/<int:retention_id>/holds", methods=["POST"])
@jwt_required()
def place_hold(retention_id):
    actor = _admin()
    record = _retention(retention_id, actor, lock=True)
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"reason"}:
        abort(400)
    reason = data["reason"]
    if (not isinstance(reason, str) or not 15 <= len(reason.strip()) <= 500
            or any(ord(ch) < 32 for ch in reason)):
        abort(400, description="Specific legal hold reason required")
    hold = EvidenceLegalHold(
        retention_id=record.id, organization_id=actor.organization_id,
        reason=reason.strip(), requested_by_id=actor.id,
    )
    db.session.add(hold)
    db.session.flush()
    enqueue(
        event_type="evidence.hold.placed", aggregate_type="evidence_hold",
        aggregate_id=hold.id, organization_id=actor.organization_id,
        actor_id=actor.id, action="evidence.hold.placed",
        idempotency_key="evidence-hold:%s" % hold.id,
    )
    db.session.commit()
    return jsonify({"id": hold.id, "retention_id": record.id, "active": True}), 201


@evidence_preservation_api.route("/holds/<int:hold_id>/release", methods=["POST"])
@jwt_required()
def release_hold(hold_id):
    actor = _admin()
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"reason"}:
        abort(400, description="Documented hold release reason required")
    reason = data["reason"]
    if (not isinstance(reason, str) or not 15 <= len(reason.strip()) <= 500
            or any(ord(ch) < 32 for ch in reason)):
        abort(400, description="Specific legal hold release reason required")
    hold = EvidenceLegalHold.query.filter_by(
        id=hold_id, organization_id=actor.organization_id
    ).with_for_update().first()
    if hold is None:
        abort(404)
    if hold.released_at is not None:
        abort(409, description="Hold already released")
    if actor.id == hold.requested_by_id:
        abort(403, description="Independent administrator required")
    hold.released_by_id = actor.id
    hold.released_at = datetime.utcnow()
    hold.release_reason = reason.strip()
    enqueue(
        event_type="evidence.hold.released", aggregate_type="evidence_hold",
        aggregate_id=hold.id, organization_id=actor.organization_id,
        actor_id=actor.id, action="evidence.hold.released",
        idempotency_key="evidence-hold-release:%s" % hold.id,
    )
    db.session.commit()
    return jsonify({"id": hold.id, "active": False})


@evidence_preservation_api.route("/retentions/<int:retention_id>/checkpoints", methods=["GET"])
@jwt_required()
def list_checkpoints(retention_id):
    actor = _admin()
    item = _retention(retention_id, actor)
    rows = EvidenceCheckpoint.query.filter_by(
        retention_id=item.id, organization_id=actor.organization_id
    ).order_by(EvidenceCheckpoint.id.desc()).limit(100).all()
    result = jsonify([{
        "id": row.id, "key_id": row.key_id,
        "payload": row.payload, "signature": row.signature,
        "algorithm": row.algorithm,
    } for row in rows])
    result.headers["Cache-Control"] = "private, no-store"
    return result
