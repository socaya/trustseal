"""Idempotency records for trust-critical client mutations.

One row per ``(tenant_id, endpoint, key)``. A locked row means an in-flight
request holding the key; a completed row holds the exact response bytes to
replay on retry. See ADR 0004.

Rows are append-only after completion. Pruning is operator-driven through
``flask retention prune-idempotency``.
"""
from datetime import datetime

from app.extensions import db


class IdempotencyRecord(db.Model):
    __tablename__ = "idempotency_records"

    id = db.Column(db.BigInteger, primary_key=True)
    tenant_id = db.Column(db.Integer, nullable=False, index=True)
    endpoint = db.Column(db.String(160), nullable=False)
    key = db.Column(db.String(128), nullable=False)
    request_hash = db.Column(db.String(64), nullable=False)
    response_status = db.Column(db.Integer)
    response_body = db.Column(db.JSON)
    response_headers = db.Column(db.JSON)
    state = db.Column(db.String(16), nullable=False, default="locked")
    locked_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)

    __table_args__ = (
        db.UniqueConstraint(
            "tenant_id", "endpoint", "key", name="uq_idempotency_tenant_endpoint_key"
        ),
        db.CheckConstraint(
            "state IN ('locked','completed','failed')",
            name="ck_idempotency_state",
        ),
    )
