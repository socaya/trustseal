"""Durable fixed-window rate-limit counters.

Each row counts hits for one ``(bucket_key, window_start)`` pair. The
counter is an upsert: each ``consume`` increments the row's ``hits``
inside a ``SELECT ... FOR UPDATE`` transaction so parallel workers
converge to the same ceiling.

Rows older than ``window_start + window_seconds`` are pruned by the
retention CLI; the rate limiter never deletes rows itself.
"""
from datetime import datetime

from app.extensions import db


class RateLimitBucket(db.Model):
    __tablename__ = "rate_limit_buckets"

    id = db.Column(db.BigInteger, primary_key=True)
    bucket_key = db.Column(db.String(160), nullable=False)
    window_start = db.Column(db.DateTime, nullable=False)
    window_seconds = db.Column(db.Integer, nullable=False)
    hits = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint(
            "bucket_key", "window_start",
            name="uq_rate_limit_bucket_key_window",
        ),
        db.CheckConstraint("hits >= 0", name="ck_rate_limit_hits_nonneg"),
        db.CheckConstraint(
            "window_seconds > 0", name="ck_rate_limit_window_positive"
        ),
    )
