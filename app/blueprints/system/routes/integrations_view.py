"""Admin view: webhook endpoints + their recent deliveries.

Read-only. Admin-gated. Links to the existing webhook API for creating,
rotating or disabling endpoints (which already has its own auth guards).
"""
from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, abort, render_template
from flask_login import current_user, login_required
from sqlalchemy import desc, func

from app.extensions import db
from app.models.user import User
from app.models.webhook import WebhookDelivery, WebhookEndpoint
from app.policies.api_access import is_admin


integrations_views = Blueprint(
    "integrations_views", __name__, url_prefix="/admin/integrations"
)


def _admin():
    if not current_user.is_authenticated:
        abort(401)
    if current_user.organization_id is None:
        abort(403, description="organization_required")
    if not is_admin(current_user.id):
        abort(403, description="admin_required")
    return current_user


@integrations_views.route("", methods=["GET"])
@login_required
def index():
    actor = _admin()

    endpoints = (
        WebhookEndpoint.query
        .filter_by(organization_id=actor.organization_id)
        .order_by(WebhookEndpoint.id.desc())
        .all()
    )
    creator_ids = {e.created_by_id for e in endpoints if e.created_by_id}
    creators = {
        u.id: u
        for u in User.query.filter(User.id.in_(creator_ids)).all()
    } if creator_ids else {}

    deliveries = (
        WebhookDelivery.query
        .filter_by(organization_id=actor.organization_id)
        .order_by(desc(WebhookDelivery.id))
        .limit(100)
        .all()
    )

    counts_by_status = {
        row.status: row.n
        for row in db.session.query(
            WebhookDelivery.status, func.count().label("n")
        )
        .filter(WebhookDelivery.organization_id == actor.organization_id)
        .group_by(WebhookDelivery.status)
        .all()
    }

    return render_template(
        "admin/integrations.html",
        endpoints=endpoints,
        creators=creators,
        deliveries=deliveries,
        counts_by_status=counts_by_status,
        now=datetime.now(timezone.utc),
    )
