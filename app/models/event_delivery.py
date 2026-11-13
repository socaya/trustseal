"""Transactional outbox and attributable security events.

Outbox payloads must contain identifiers only, never secrets or raw documents.
At-least-once delivery requires idempotent downstream handlers.
"""
from datetime import datetime
from app.extensions import db


class SecurityEvent(db.Model):
    __tablename__ = "security_events"
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    action = db.Column(db.String(100), nullable=False)
    resource_type = db.Column(db.String(60), nullable=False)
    resource_id = db.Column(db.Integer)
    outcome = db.Column(db.String(24), nullable=False, default="success")
    correlation_id = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class OutboxEvent(db.Model):
    __tablename__ = "outbox_events"
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    event_type = db.Column(db.String(100), nullable=False)
    aggregate_type = db.Column(db.String(60), nullable=False)
    aggregate_id = db.Column(db.Integer, nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), index=True)
    payload = db.Column(db.JSON, nullable=False)
    idempotency_key = db.Column(db.String(128), nullable=False, unique=True)
    state = db.Column(db.String(24), nullable=False, default="pending", index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    next_attempt_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    locked_until = db.Column(db.DateTime)
    lease_token = db.Column(db.String(36), index=True)
    last_error = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    __table_args__ = (
        db.CheckConstraint("attempts >= 0", name="ck_outbox_attempts"),
        db.CheckConstraint("state IN ('pending','processing','completed','dead')", name="ck_outbox_state"),
    )
