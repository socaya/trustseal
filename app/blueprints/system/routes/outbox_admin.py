"""Outbox dead-letter inspection + replay (P1).

Operators sometimes need to inspect and re-drive events that
exhausted their retry budget. This blueprint exposes two
tenant-scoped admin endpoints:

* ``GET /api/_internal/outbox/dead`` — list dead outbox events
  (and optionally failed events still in retry state).
* ``POST /api/_internal/outbox/dead/<id>/replay`` — flip the event
  back to ``pending`` with ``attempts=0`` and ``next_attempt_at=now``
  so the standard worker picks it up.

The service never mutates cross-tenant rows; the admin's
organization scopes every query.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from flask import Blueprint, abort, jsonify, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.event_delivery import OutboxEvent, SecurityEvent
from app.policies.api_access import is_admin
from app.services.token_security import active_token_user


outbox_admin_api = Blueprint(
    "outbox_admin_api", __name__, url_prefix="/api/_internal/outbox"
)


def _admin():
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    if not is_admin(user.id):
        abort(403, description="admin_required")
    if user.organization_id is None:
        abort(403, description="organization_required")
    return user


def _dict(row: OutboxEvent) -> dict:
    return {
        "id": row.id,
        "event_type": row.event_type,
        "aggregate_type": row.aggregate_type,
        "aggregate_id": row.aggregate_id,
        "state": row.state,
        "attempts": row.attempts,
        "last_error": row.last_error,
        "next_attempt_at": row.next_attempt_at.isoformat()
        if row.next_attempt_at
        else None,
        "created_at": row.created_at.isoformat(),
        "completed_at": row.completed_at.isoformat()
        if row.completed_at
        else None,
    }


@outbox_admin_api.route("/dead", methods=["GET"])
@jwt_required()
def list_dead():
    user = _admin()
    include_failed = request.args.get("include_failed") == "1"
    states = ["dead"]
    if include_failed:
        states.append("pending")  # events that are in retry backoff
    rows = (
        OutboxEvent.query.filter(
            OutboxEvent.organization_id == user.organization_id,
            OutboxEvent.state.in_(states),
        )
        .order_by(OutboxEvent.id.desc())
        .limit(200)
        .all()
    )
    if not include_failed:
        rows = [r for r in rows if r.state == "dead"]
    return jsonify(events=[_dict(r) for r in rows])


@outbox_admin_api.route("/dead/<int:event_id>/replay", methods=["POST"])
@jwt_required()
def replay_dead(event_id: int):
    user = _admin()
    row = (
        OutboxEvent.query.filter_by(
            id=event_id, organization_id=user.organization_id
        )
        .with_for_update()
        .first()
    )
    if row is None:
        abort(404)
    if row.state == "completed":
        abort(409, description="event_already_completed")
    row.state = "pending"
    row.attempts = 0
    row.last_error = None
    row.next_attempt_at = datetime.utcnow()
    row.locked_until = None
    row.lease_token = None
    db.session.add(
        SecurityEvent(
            organization_id=user.organization_id,
            actor_id=user.id,
            action="outbox.dead_letter_replayed",
            resource_type="outbox_event",
            resource_id=row.id,
            outcome="ok",
            correlation_id=uuid.uuid4().hex,
        )
    )
    db.session.commit()
    return jsonify(_dict(row))
