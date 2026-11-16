"""Operator admin dashboard aggregator (P2).

``GET /api/_internal/dashboard`` returns a single JSON document that
rolls up everything the tenant admin UI needs for a one-page view:

* Readiness probe (DB + alembic + storage + mail transport).
* SLO observations per endpoint class (if available).
* Usage summary (current period per meter).
* Outbox backlog (counts per state).
* Webhook delivery backlog (counts per state).

Scoped to the caller's organization. Admin-only.
"""
from __future__ import annotations

from flask import Blueprint, abort, jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy import func

from app.extensions import db
from app.models.event_delivery import OutboxEvent
from app.models.webhook import WebhookDelivery
from app.policies.api_access import is_admin
from app.services import slo, usage_ledger
from app.services.token_security import active_token_user


admin_dashboard_api = Blueprint(
    "admin_dashboard_api", __name__, url_prefix="/api/_internal"
)


@admin_dashboard_api.route("/dashboard", methods=["GET"])
@jwt_required()
def dashboard():
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    if not is_admin(user.id):
        abort(403, description="admin_required")
    if user.organization_id is None:
        abort(403, description="organization_required")
    return jsonify(
        organization_id=user.organization_id,
        readiness=_readiness_summary(),
        slo=_slo_summary(),
        usage=_usage_summary(user.organization_id),
        outbox=_outbox_backlog(user.organization_id),
        webhooks=_webhook_backlog(user.organization_id),
    )


def _readiness_summary() -> dict:
    """Aggregate /ready output without a second HTTP round-trip."""
    from app.blueprints.system.routes.health import (
        _db_check,
        _mail_transport_check,
        _migrations_check,
        _private_storage_check,
    )

    checks = [
        _db_check(),
        _migrations_check(),
        _private_storage_check(),
        _mail_transport_check(),
    ]
    overall = all(c.get("status") == "ok" for c in checks)
    return {"status": "ok" if overall else "degraded", "checks": checks}


def _slo_summary() -> list[dict]:
    observations = slo.observations()
    return [
        {
            "endpoint_class": o.endpoint_class,
            "status": o.status,
            "availability_observed": o.availability_observed,
            "availability_target": o.availability_target,
            "latency_p95_observed_ms": o.latency_p95_observed_ms,
            "latency_p95_target_ms": o.latency_p95_target_ms,
            "burn_rate": o.burn_rate,
        }
        for o in observations
    ]


def _usage_summary(organization_id: int) -> dict:
    try:
        meters = usage_ledger.summary(organization_id, period="month")
    except usage_ledger.UsageError:
        return {}
    return meters


def _outbox_backlog(organization_id: int) -> dict:
    rows = (
        db.session.query(OutboxEvent.state, func.count(OutboxEvent.id))
        .filter(OutboxEvent.organization_id == organization_id)
        .group_by(OutboxEvent.state)
        .all()
    )
    return {state: int(count) for state, count in rows}


def _webhook_backlog(organization_id: int) -> dict:
    rows = (
        db.session.query(WebhookDelivery.status, func.count(WebhookDelivery.id))
        .filter(WebhookDelivery.organization_id == organization_id)
        .group_by(WebhookDelivery.status)
        .all()
    )
    return {status: int(count) for status, count in rows}
