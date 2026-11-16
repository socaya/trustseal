"""Operator notification API (Phase W1).

Endpoints:

* ``GET  /api/notifications`` — list notifications for the caller.
  Query: ``unread=1`` to restrict to unread, ``limit`` (1..500).
* ``GET  /api/notifications/count`` — unread count.
* ``POST /api/notifications/<id>/read`` — mark one row as read.
* ``POST /api/notifications/read-all`` — mark every unread row read.

All endpoints are tenant-scoped to ``user.organization_id`` and
filtered to rows whose ``recipient_user_id`` matches the caller.
"""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.services import operator_notifications as notifications
from app.services.token_security import active_token_user


operator_notifications_api = Blueprint(
    "operator_notifications_api",
    __name__,
    url_prefix="/api/notifications",
)


def _actor():
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    if user.organization_id is None:
        abort(403, description="organization_required")
    return user


def _dict(row) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "subject_type": row.subject_type,
        "subject_id": row.subject_id,
        "summary": row.summary,
        "created_at": row.created_at.isoformat(),
        "read_at": row.read_at.isoformat() if row.read_at else None,
    }


@operator_notifications_api.route("", methods=["GET"])
@jwt_required()
def list_notifications():
    user = _actor()
    unread_only = request.args.get("unread") == "1"
    limit_raw = request.args.get("limit")
    try:
        limit = int(limit_raw) if limit_raw else 100
    except ValueError:
        abort(400, description="limit_invalid")
    if limit < 1 or limit > 500:
        abort(400, description="limit_out_of_range")
    rows = notifications.list_for(
        recipient_user_id=user.id,
        organization_id=user.organization_id,
        unread_only=unread_only,
        limit=limit,
    )
    return jsonify(
        recipient_user_id=user.id,
        unread_only=unread_only,
        notifications=[_dict(r) for r in rows],
    )


@operator_notifications_api.route("/count", methods=["GET"])
@jwt_required()
def count_unread():
    user = _actor()
    return jsonify(
        recipient_user_id=user.id,
        unread=notifications.count_unread(
            recipient_user_id=user.id,
            organization_id=user.organization_id,
        ),
    )


@operator_notifications_api.route("/<int:notification_id>/read", methods=["POST"])
@jwt_required()
def mark_read(notification_id: int):
    user = _actor()
    row = notifications.mark_read(
        notification_id=notification_id,
        recipient_user_id=user.id,
        organization_id=user.organization_id,
    )
    if row is None:
        abort(404)
    db.session.commit()
    return jsonify(_dict(row))


@operator_notifications_api.route("/read-all", methods=["POST"])
@jwt_required()
def mark_all_read():
    user = _actor()
    updated = notifications.mark_all_read(
        recipient_user_id=user.id,
        organization_id=user.organization_id,
    )
    db.session.commit()
    return jsonify(updated=updated)
