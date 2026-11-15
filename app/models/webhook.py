"""Webhook endpoints and delivery records.

An endpoint is a per-tenant subscription: a URL that receives signed
POST deliveries for a selected set of event types. Each outbound POST
is recorded as a :class:`WebhookDelivery` row so operators can inspect
history, replay failures, and discover misconfigured receivers.

Deliveries are append-only. Status transitions are:

    pending -> in_flight -> succeeded
                       \\-> failed -> (retry) pending
                       \\-> dead

The ``retry_count`` + ``next_retry_at`` fields drive the exponential
backoff schedule; the dispatcher picks eligible rows ordered by
``next_retry_at``.
"""
from datetime import datetime

from app.extensions import db


class WebhookEndpoint(db.Model):
    __tablename__ = "webhook_endpoints"

    id = db.Column(db.BigInteger, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    url = db.Column(db.String(512), nullable=False)
    secret_hash = db.Column(db.String(128), nullable=False)
    events = db.Column(db.JSON, nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    description = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        db.UniqueConstraint(
            "organization_id", "url", name="uq_webhook_endpoint_org_url"
        ),
    )


class WebhookDelivery(db.Model):
    __tablename__ = "webhook_deliveries"

    id = db.Column(db.BigInteger, primary_key=True)
    endpoint_id = db.Column(
        db.BigInteger,
        db.ForeignKey("webhook_endpoints.id"),
        nullable=False,
        index=True,
    )
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    event_id = db.Column(db.String(64), nullable=False)
    event_type = db.Column(db.String(80), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    status = db.Column(db.String(16), nullable=False, default="pending")
    retry_count = db.Column(db.Integer, nullable=False, default=0)
    next_retry_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    response_status = db.Column(db.Integer)
    response_excerpt = db.Column(db.String(400))
    last_error = db.Column(db.String(400))
    sent_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint(
            "endpoint_id", "event_id", name="uq_webhook_delivery_endpoint_event"
        ),
        db.CheckConstraint(
            "status IN ('pending','in_flight','succeeded','failed','dead')",
            name="ck_webhook_delivery_status",
        ),
        db.CheckConstraint("retry_count >= 0", name="ck_webhook_delivery_retries"),
    )
