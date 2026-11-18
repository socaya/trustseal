"""TSD Stamp Studio API — tenant-owned SVG stamp designs.

Admin-free: anyone in the tenant can design + register a stamp for
inline insertion into TSDs. The heavier
``managed_stamps``/``stamp_design_versions`` workflow (custody,
approval, PDF appearance) stays untouched for cryptographically-
attested PDF sealing.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from flask import Blueprint, abort, jsonify, request
from flask_login import current_user, login_required

from app.extensions import db
from app.models.event_delivery import SecurityEvent
from app.models.tsd_stamp import TSD_STAMP_KINDS, TSDStamp


tsd_stamps_api = Blueprint("tsd_stamps_api", __name__, url_prefix="/api/tsd-stamps")


def _actor():
    if not current_user.is_authenticated:
        abort(401)
    if current_user.organization_id is None:
        abort(403, description="organization_required")
    return current_user


def _emit(action: str, resource_id: int, outcome: str = "success") -> None:
    db.session.add(SecurityEvent(
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action=action,
        resource_type="tsd_stamp",
        resource_id=resource_id,
        outcome=outcome,
        correlation_id=uuid.uuid4().hex,
    ))


@tsd_stamps_api.route("/", methods=["GET"])
@login_required
def list_stamps():
    actor = _actor()
    rows = (
        TSDStamp.query
        .filter(TSDStamp.organization_id == actor.organization_id,
                TSDStamp.deleted_at.is_(None))
        .order_by(TSDStamp.updated_at.desc())
        .all()
    )
    include_svg = (request.args.get("include_svg", "1") != "0")
    return jsonify([r.to_dict(include_svg=include_svg) for r in rows])


@tsd_stamps_api.route("/", methods=["POST"])
@login_required
def create_stamp():
    actor = _actor()
    payload = request.get_json(silent=True) or {}

    name = (payload.get("name") or "").strip()
    kind = (payload.get("kind") or "seal").lower()
    layout = payload.get("layout") or {}
    svg = (payload.get("svg") or "").strip()

    if not name:
        return jsonify({"error": "name_required"}), 400
    if len(name) > 120:
        return jsonify({"error": "name_too_long", "max": 120}), 400
    if kind not in TSD_STAMP_KINDS:
        return jsonify({"error": "invalid_kind",
                        "allowed": list(TSD_STAMP_KINDS)}), 400
    if not isinstance(layout, dict):
        return jsonify({"error": "layout_must_be_object"}), 400
    if not svg.startswith("<svg") or not svg.endswith("</svg>"):
        return jsonify({"error": "svg_invalid"}), 400
    if len(svg) > 32 * 1024:
        return jsonify({"error": "svg_too_large", "max": 32 * 1024}), 400

    row = TSDStamp(
        organization_id=actor.organization_id,
        created_by_id=actor.id,
        name=name,
        kind=kind,
        layout=layout,
        svg=svg,
    )
    db.session.add(row)
    try:
        db.session.flush()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "duplicate_name"}), 409

    _emit("tsd.stamp_register", row.id, outcome=kind)
    db.session.commit()
    return jsonify(row.to_dict()), 201


@tsd_stamps_api.route("/<int:stamp_id>", methods=["PUT"])
@login_required
def update_stamp(stamp_id: int):
    actor = _actor()
    row = (
        TSDStamp.query
        .filter(TSDStamp.id == stamp_id,
                TSDStamp.organization_id == actor.organization_id,
                TSDStamp.deleted_at.is_(None))
        .first()
    )
    if row is None:
        abort(404)

    payload = request.get_json(silent=True) or {}
    if "name" in payload:
        n = (payload["name"] or "").strip()
        if not n or len(n) > 120:
            return jsonify({"error": "name_invalid"}), 400
        row.name = n
    if "kind" in payload:
        if payload["kind"] not in TSD_STAMP_KINDS:
            return jsonify({"error": "invalid_kind"}), 400
        row.kind = payload["kind"]
    if "layout" in payload:
        if not isinstance(payload["layout"], dict):
            return jsonify({"error": "layout_must_be_object"}), 400
        row.layout = payload["layout"]
    if "svg" in payload:
        s = (payload["svg"] or "").strip()
        if not s.startswith("<svg") or not s.endswith("</svg>"):
            return jsonify({"error": "svg_invalid"}), 400
        if len(s) > 32 * 1024:
            return jsonify({"error": "svg_too_large", "max": 32 * 1024}), 400
        row.svg = s

    _emit("tsd.stamp_update", row.id)
    db.session.commit()
    return jsonify(row.to_dict())


@tsd_stamps_api.route("/<int:stamp_id>", methods=["DELETE"])
@login_required
def delete_stamp(stamp_id: int):
    actor = _actor()
    row = (
        TSDStamp.query
        .filter(TSDStamp.id == stamp_id,
                TSDStamp.organization_id == actor.organization_id,
                TSDStamp.deleted_at.is_(None))
        .first()
    )
    if row is None:
        abort(404)
    row.deleted_at = datetime.utcnow()
    _emit("tsd.stamp_delete", row.id)
    db.session.commit()
    return "", 204
