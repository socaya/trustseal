"""Webhook endpoint management API.

Every mutation is tenant-scoped and routed through the policy guard.
The one-time ``secret`` is returned from ``POST /api/webhooks`` and
``POST /api/webhooks/<id>/rotate`` only; subsequent reads never
disclose it.
"""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.webhook import WebhookDelivery, WebhookEndpoint
from app.policies.authorization import current_actor
from app.services.idempotency import idempotent
from app.services.webhooks import (
    WebhookError,
    deactivate,
    register_endpoint,
    rotate_secret,
)

webhook_api = Blueprint("webhook_api", __name__, url_prefix="/api/webhooks")


def _endpoint_dict(endpoint: WebhookEndpoint) -> dict:
    return {
        "id": endpoint.id,
        "url": endpoint.url,
        "events": list(endpoint.events or []),
        "active": bool(endpoint.active),
        "description": endpoint.description,
        "created_by_id": endpoint.created_by_id,
        "created_at": endpoint.created_at.isoformat() if endpoint.created_at else None,
        "updated_at": endpoint.updated_at.isoformat() if endpoint.updated_at else None,
    }


def _delivery_dict(delivery: WebhookDelivery) -> dict:
    return {
        "id": delivery.id,
        "endpoint_id": delivery.endpoint_id,
        "event_id": delivery.event_id,
        "event_type": delivery.event_type,
        "status": delivery.status,
        "retry_count": delivery.retry_count,
        "response_status": delivery.response_status,
        "last_error": delivery.last_error,
        "next_retry_at": delivery.next_retry_at.isoformat()
        if delivery.next_retry_at
        else None,
        "sent_at": delivery.sent_at.isoformat() if delivery.sent_at else None,
        "completed_at": delivery.completed_at.isoformat()
        if delivery.completed_at
        else None,
        "created_at": delivery.created_at.isoformat() if delivery.created_at else None,
    }


def _tenant_endpoint(endpoint_id: int) -> WebhookEndpoint:
    actor = current_actor()
    if actor.tenant_id is None:
        abort(403)
    item = WebhookEndpoint.query.filter_by(
        id=endpoint_id, organization_id=actor.tenant_id
    ).first()
    if item is None:
        abort(404)
    return item


@webhook_api.route("", methods=["GET"])
@jwt_required()
def list_endpoints():
    actor = current_actor()
    if actor.tenant_id is None:
        abort(403)
    rows = (
        WebhookEndpoint.query.filter_by(organization_id=actor.tenant_id)
        .order_by(WebhookEndpoint.id.desc())
        .limit(100)
        .all()
    )
    return jsonify([_endpoint_dict(r) for r in rows])


@webhook_api.route("", methods=["POST"])
@jwt_required()
@idempotent("webhooks.create")
def create_endpoint():
    actor = current_actor()
    if actor.tenant_id is None:
        abort(403)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="json_object_required")
    url = data.get("url")
    events = data.get("events")
    description = data.get("description")
    if not isinstance(events, list):
        abort(400, description="events_must_be_list")
    try:
        endpoint, secret = register_endpoint(
            tenant_id=actor.tenant_id,
            created_by_id=actor.user_id,
            url=url,
            events=events,
            description=description if isinstance(description, str) else None,
        )
    except WebhookError as exc:
        abort(400, description=str(exc))
    db.session.commit()
    body = _endpoint_dict(endpoint)
    body["secret"] = secret
    body["secret_disclosure_once"] = True
    response = jsonify(body)
    response.status_code = 201
    return response


@webhook_api.route("/<int:endpoint_id>", methods=["GET"])
@jwt_required()
def get_endpoint(endpoint_id: int):
    return jsonify(_endpoint_dict(_tenant_endpoint(endpoint_id)))


@webhook_api.route("/<int:endpoint_id>", methods=["DELETE"])
@jwt_required()
def deactivate_endpoint(endpoint_id: int):
    endpoint = _tenant_endpoint(endpoint_id)
    deactivate(endpoint)
    db.session.commit()
    return jsonify(_endpoint_dict(endpoint))


@webhook_api.route("/<int:endpoint_id>/rotate", methods=["POST"])
@jwt_required()
@idempotent("webhooks.rotate")
def rotate_endpoint_secret(endpoint_id: int):
    endpoint = _tenant_endpoint(endpoint_id)
    secret = rotate_secret(endpoint)
    db.session.commit()
    body = _endpoint_dict(endpoint)
    body["secret"] = secret
    body["secret_disclosure_once"] = True
    return jsonify(body)


@webhook_api.route("/<int:endpoint_id>/ping", methods=["POST"])
@jwt_required()
@idempotent("webhooks.ping")
def ping_endpoint(endpoint_id: int):
    """Enqueue a synthetic ``trustseal.ping`` for the endpoint."""
    from app.services.webhooks import enqueue_ping

    endpoint = _tenant_endpoint(endpoint_id)
    delivery = enqueue_ping(endpoint)
    db.session.commit()
    return jsonify(_delivery_dict(delivery)), 201


@webhook_api.route(
    "/deliveries/<int:delivery_id>/replay", methods=["POST"]
)
@jwt_required()
@idempotent("webhooks.deliveries.replay")
def replay_webhook_delivery(delivery_id: int):
    """Re-fire a specific delivery (any status, including dead)."""
    from app.services.webhooks import replay_delivery

    actor = current_actor()
    if actor.tenant_id is None:
        abort(403)
    original = WebhookDelivery.query.filter_by(
        id=delivery_id, organization_id=actor.tenant_id
    ).one_or_none()
    if original is None:
        abort(404)
    replay = replay_delivery(original)
    db.session.commit()
    return jsonify(_delivery_dict(replay)), 201


@webhook_api.route(
    "/deliveries/<int:delivery_id>/cancel", methods=["POST"]
)
@jwt_required()
def cancel_webhook_delivery(delivery_id: int):
    """Operator-initiated delivery cancellation (Phase AB2).

    Marks a pending or failed delivery as ``dead`` so the dispatcher
    stops retrying it. Succeeded deliveries, in-flight deliveries,
    and already-dead rows return 409 — operators should either wait
    for in-flight work to settle or skip rows that are already
    finalised.
    """
    from datetime import datetime

    actor = current_actor()
    if actor.tenant_id is None:
        abort(403)
    delivery = (
        WebhookDelivery.query.filter_by(
            id=delivery_id, organization_id=actor.tenant_id
        )
        .with_for_update()
        .one_or_none()
    )
    if delivery is None:
        abort(404)
    if delivery.status not in {"pending", "failed"}:
        abort(409, description="delivery_not_cancellable")
    delivery.status = "dead"
    delivery.last_error = "operator_cancelled"
    delivery.completed_at = datetime.utcnow()
    db.session.commit()
    return jsonify(_delivery_dict(delivery)), 200


@webhook_api.route("/<int:endpoint_id>/deliveries", methods=["GET"])
@jwt_required()
def list_deliveries(endpoint_id: int):
    _tenant_endpoint(endpoint_id)  # 404 if the endpoint isn't in this tenant
    rows = (
        WebhookDelivery.query.filter_by(endpoint_id=endpoint_id)
        .order_by(WebhookDelivery.id.desc())
        .limit(100)
        .all()
    )
    return jsonify([_delivery_dict(r) for r in rows])
