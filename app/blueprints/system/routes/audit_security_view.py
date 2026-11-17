"""Admin viewer for SecurityEvent (chained-hash audit log) + Outbox state.

Dedicated HTML view. Admin-only. Read-only.
"""
from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, abort, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import desc

from app.extensions import db
from app.models.event_delivery import OutboxEvent, SecurityEvent
from app.models.user import User
from app.policies.api_access import is_admin


audit_security_views = Blueprint(
    "audit_security_views", __name__, url_prefix="/admin/audit"
)


def _admin():
    if not current_user.is_authenticated:
        abort(401)
    if current_user.organization_id is None:
        abort(403, description="organization_required")
    if not is_admin(current_user.id):
        abort(403, description="admin_required")
    return current_user


@audit_security_views.route("", methods=["GET"])
@login_required
def index():
    actor = _admin()

    try:
        limit = min(max(int(request.args.get("limit", 100)), 10), 500)
    except (TypeError, ValueError):
        limit = 100
    action_filter = (request.args.get("action") or "").strip()
    outcome_filter = (request.args.get("outcome") or "").strip()

    events_q = (
        SecurityEvent.query
        .filter_by(organization_id=actor.organization_id)
    )
    if action_filter:
        events_q = events_q.filter(SecurityEvent.action == action_filter)
    if outcome_filter:
        events_q = events_q.filter(SecurityEvent.outcome == outcome_filter)
    events = events_q.order_by(desc(SecurityEvent.id)).limit(limit).all()

    actor_ids = {e.actor_id for e in events if e.actor_id}
    actors = {
        u.id: u
        for u in User.query.filter(User.id.in_(actor_ids)).all()
    } if actor_ids else {}

    outbox = (
        OutboxEvent.query
        .filter_by(organization_id=actor.organization_id)
        .order_by(desc(OutboxEvent.id))
        .limit(50)
        .all()
    )

    counts_by_state = {
        row.state: row.n
        for row in db.session.query(
            OutboxEvent.state, db.func.count().label("n")
        )
        .filter(OutboxEvent.organization_id == actor.organization_id)
        .group_by(OutboxEvent.state)
        .all()
    }

    return render_template(
        "admin/audit_security.html",
        events=events,
        actors=actors,
        outbox=outbox,
        counts_by_state=counts_by_state,
        limit=limit,
        action_filter=action_filter,
        outcome_filter=outcome_filter,
        now=datetime.now(timezone.utc),
    )
