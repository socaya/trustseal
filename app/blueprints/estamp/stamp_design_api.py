"""Tenant-scoped, independently approved graphical stamp designs."""
from datetime import datetime
from io import BytesIO

from flask import Blueprint, abort, jsonify, request, send_file
from flask_jwt_extended import jwt_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.stamp_design import StampDesignVersion
from app.models.stamp_custody import ManagedStamp
from app.services.token_security import active_token_user
from app.policies.api_access import is_admin
from app.services.stamp_designs import (
    validate_layout, normalize_png, design_digest, checked_design,
)
from app.services.event_delivery import enqueue

stamp_design_api = Blueprint("stamp_design_api", __name__, url_prefix="/api/stamp-designs")


def _actor():
    actor = active_token_user()
    if actor is None or not actor.is_active or actor.organization_id is None:
        abort(401)
    return actor


def _stamp(stamp_id, user, lock=False):
    q = ManagedStamp.query.filter_by(id=stamp_id, organization_id=user.organization_id)
    stamp = (q.with_for_update() if lock else q).first()
    if stamp is None:
        abort(404)
    if not is_admin(user.id) and user.id not in (stamp.custodian_id, stamp.created_by_id):
        abort(404)
    return stamp


def _design(design_id, user):
    design = StampDesignVersion.query.filter_by(
        id=design_id, organization_id=user.organization_id
    ).first()
    if design is None:
        abort(404)
    stamp = _stamp(design.stamp_id, user)
    return design, stamp


def _serialize(item):
    return {
        "id": item.id, "stamp_id": item.stamp_id,
        "version": item.version, "layout": item.layout,
        "logo_sha256": item.logo_sha256,
        "design_sha256": item.design_sha256,
        "state": item.state, "created_by_id": item.created_by_id,
        "approved_by_id": item.approved_by_id,
        "approved_at": item.approved_at.isoformat() if item.approved_at else None,
    }


@stamp_design_api.route("/stamps/<int:stamp_id>", methods=["POST"])
@jwt_required()
def propose_design(stamp_id):
    actor = _actor()
    stamp = _stamp(stamp_id, actor, lock=True)
    if stamp.status != "active" or actor.id != stamp.custodian_id:
        abort(403, description="Active stamp custodian required")
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"layout", "logo_png_b64"}:
        abort(400, description="Expected layout and optional logo")
    try:
        layout = validate_layout(data["layout"])
        normalized, fingerprint = normalize_png(data["logo_png_b64"])
        digest = design_digest(layout, fingerprint)
    except (ValueError, TypeError, KeyError):
        abort(400, description="Invalid stamp design")
    latest = db.session.query(func.max(StampDesignVersion.version)).filter_by(
        stamp_id=stamp.id
    ).scalar() or 0
    item = StampDesignVersion(
        stamp_id=stamp.id, organization_id=actor.organization_id,
        version=latest + 1, layout=layout, logo_png_b64=normalized,
        logo_sha256=fingerprint, design_sha256=digest,
        created_by_id=actor.id, state="pending",
    )
    db.session.add(item)
    try:
        db.session.flush()
        enqueue(
            event_type="stamp.design.proposed", aggregate_type="stamp",
            aggregate_id=stamp.id, organization_id=stamp.organization_id,
            actor_id=actor.id, action="stamp.design.proposed",
            idempotency_key="stamp-design-proposed:%s" % item.id,
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        abort(409, description="Concurrent design version conflict")
    return jsonify(_serialize(item)), 201


@stamp_design_api.route("/stamps/<int:stamp_id>", methods=["GET"])
@jwt_required()
def list_designs(stamp_id):
    actor = _actor()
    _stamp(stamp_id, actor)
    items = StampDesignVersion.query.filter_by(
        stamp_id=stamp_id, organization_id=actor.organization_id
    ).order_by(StampDesignVersion.version.desc()).limit(100).all()
    return jsonify([_serialize(item) for item in items])


@stamp_design_api.route("/<int:design_id>/decision", methods=["POST"])
@jwt_required()
def decide_design(design_id):
    actor = _actor()
    if not is_admin(actor.id):
        abort(403)
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"decision"} or data["decision"] not in ("approved", "rejected"):
        abort(400)
    item = StampDesignVersion.query.filter_by(
        id=design_id, organization_id=actor.organization_id
    ).with_for_update().first()
    if item is None:
        abort(404)
    stamp = _stamp(item.stamp_id, actor)
    if item.state != "pending" or stamp.status != "active":
        abort(409, description="Design cannot be decided")
    if actor.id in (item.created_by_id, stamp.custodian_id):
        abort(403, description="Independent administrator required")
    try:
        checked_design(item)
    except ValueError:
        abort(409, description="Design integrity mismatch")
    item.state = data["decision"]
    item.approved_by_id = actor.id
    item.approved_at = datetime.utcnow()
    enqueue(
        event_type="stamp.design." + data["decision"],
        aggregate_type="stamp", aggregate_id=stamp.id,
        organization_id=stamp.organization_id,
        actor_id=actor.id, action="stamp.design." + data["decision"],
        idempotency_key="stamp-design-decision:%s" % item.id,
    )
    db.session.commit()
    return jsonify(_serialize(item))


@stamp_design_api.route("/<int:design_id>/preview", methods=["GET"])
@jwt_required()
def preview_design(design_id):
    actor = _actor()
    item, stamp = _design(design_id, actor)
    try:
        layout, logo = checked_design(item)
        from app.services.stamp_pdf_impression import preview_stamp_pdf
        raw = preview_stamp_pdf(
            stamp.code, stamp.name, item.version, layout, logo
        )
    except ValueError:
        abort(409, description="Design integrity mismatch")
    response = send_file(
        BytesIO(raw), mimetype="application/pdf", as_attachment=True,
        download_name="stamp-design-preview-%s.pdf" % item.id,
        conditional=False, etag=False, max_age=0,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response
