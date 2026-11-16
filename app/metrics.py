"""Prometheus metrics exposed at ``/metrics``.

Metrics intentionally stay narrow — one histogram for request latency
with ``method`` and ``path_template`` labels, counters for outbox and
webhook outcomes, and a gauge for the pending-work backlog. Add new
series only after a specific alerting or capacity-planning need, so the
cardinality stays manageable.

The exposition endpoint is admin-only. For cluster scraping, deploy a
Prometheus sidecar behind an internal network ACL or expose through a
dedicated management port.
"""
from __future__ import annotations

import time

from flask import Flask, Response, abort, g, request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# A dedicated registry keeps the exposition scoped to TrustSeal series;
# we never leak Python runtime metrics from the default registry into a
# tenant-visible endpoint.
registry: CollectorRegistry = CollectorRegistry()

http_request_duration_seconds = Histogram(
    "trustseal_http_request_duration_seconds",
    "Duration of HTTP requests by method and matched endpoint.",
    labelnames=("method", "endpoint", "status"),
    registry=registry,
)

http_requests_total = Counter(
    "trustseal_http_requests_total",
    "Total HTTP requests by method, endpoint, and status class.",
    labelnames=("method", "endpoint", "status"),
    registry=registry,
)

outbox_events_total = Counter(
    "trustseal_outbox_events_total",
    "Outbox events processed, labeled by outcome.",
    labelnames=("outcome",),
    registry=registry,
)

webhook_deliveries_total = Counter(
    "trustseal_webhook_deliveries_total",
    "Webhook delivery attempts, labeled by outcome.",
    labelnames=("outcome",),
    registry=registry,
)

idempotency_requests_total = Counter(
    "trustseal_idempotency_requests_total",
    "Idempotency-key handled requests by outcome (fresh, replayed, conflict).",
    labelnames=("outcome",),
    registry=registry,
)

operator_notifications_published_total = Counter(
    "trustseal_operator_notifications_published_total",
    "In-app operator notifications published, labeled by kind.",
    labelnames=("kind",),
    registry=registry,
)

outbox_backlog = Gauge(
    "trustseal_outbox_backlog",
    "Count of outbox events in each state.",
    labelnames=("state",),
    registry=registry,
)

webhook_backlog = Gauge(
    "trustseal_webhook_backlog",
    "Count of webhook deliveries in each state.",
    labelnames=("state",),
    registry=registry,
)


def _endpoint_label() -> str:
    """Return a stable label for the matched URL rule.

    Prefer the Flask rule (``/api/envelopes/<int:envelope_id>/prepare``)
    over the raw path so we don't explode cardinality with ids.
    """
    rule = request.url_rule
    if rule is not None:
        return str(rule.rule)
    return "<unmatched>"


def _status_label(status_code: int) -> str:
    if status_code < 200:
        return "1xx"
    if status_code < 300:
        return "2xx"
    if status_code < 400:
        return "3xx"
    if status_code < 500:
        return "4xx"
    return "5xx"


def configure_metrics(app: Flask) -> None:
    """Install request-duration instrumentation and the /metrics endpoint."""

    @app.before_request
    def _start_timer() -> None:
        g._metrics_start = time.perf_counter()

    @app.after_request
    def _record(response):
        start = getattr(g, "_metrics_start", None)
        if start is None:
            return response
        duration = time.perf_counter() - start
        labels = (
            request.method,
            _endpoint_label(),
            _status_label(response.status_code),
        )
        http_request_duration_seconds.labels(*labels).observe(duration)
        http_requests_total.labels(*labels).inc()
        return response

    @app.route("/api/metrics")
    def _metrics_endpoint():
        # Admin-only: avoid exposing counters to an anonymous caller
        # even inside a VPC. The admin check runs via the same policy
        # layer as every other API route.
        from app.policies.authorization import current_actor

        try:
            actor = current_actor()
        except Exception:
            abort(401)
        if not actor.has_role("admin", "administrator", "superadmin", "super_admin"):
            abort(403)
        _refresh_gauges()
        return Response(generate_latest(registry), mimetype=CONTENT_TYPE_LATEST)


def _refresh_gauges() -> None:
    """Snapshot the current backlog into gauges before serving."""
    from sqlalchemy import func

    from app.extensions import db
    from app.models.event_delivery import OutboxEvent
    from app.models.webhook import WebhookDelivery

    outbox_rows = (
        db.session.query(OutboxEvent.state, func.count(OutboxEvent.id))
        .group_by(OutboxEvent.state)
        .all()
    )
    seen_outbox = set()
    for state, count in outbox_rows:
        outbox_backlog.labels(state or "unknown").set(int(count))
        seen_outbox.add(state or "unknown")
    for state in ("pending", "processing", "dead"):
        if state not in seen_outbox:
            outbox_backlog.labels(state).set(0)

    webhook_rows = (
        db.session.query(WebhookDelivery.status, func.count(WebhookDelivery.id))
        .group_by(WebhookDelivery.status)
        .all()
    )
    seen_webhooks = set()
    for state, count in webhook_rows:
        webhook_backlog.labels(state or "unknown").set(int(count))
        seen_webhooks.add(state or "unknown")
    for state in ("pending", "in_flight", "succeeded", "failed", "dead"):
        if state not in seen_webhooks:
            webhook_backlog.labels(state).set(0)


# ---- helpers domain services call to bump counters directly ----


def record_outbox_outcome(outcome: str) -> None:
    outbox_events_total.labels(outcome).inc()


def record_webhook_outcome(outcome: str) -> None:
    webhook_deliveries_total.labels(outcome).inc()


def record_idempotency_outcome(outcome: str) -> None:
    idempotency_requests_total.labels(outcome).inc()


def record_operator_notification(kind: str) -> None:
    operator_notifications_published_total.labels(kind).inc()
