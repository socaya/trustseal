"""Deduplicated usage ledger.

One row per ``(organization_id, meter, source_event_id)`` so repeated
replays of the same business event never double-count. The service
layer records entries from inside the same transaction as the event
it meters, so partial writes roll back together.

Period aggregation is derived at read time from ``recorded_at`` so
the same ledger supports both monthly and daily rollups without
duplicating storage. For large deployments, a materialized view can
be added later without changing the write path.
"""
from datetime import datetime

from app.extensions import db


class UsageLedgerEntry(db.Model):
    __tablename__ = "usage_ledger_entries"

    id = db.Column(db.BigInteger, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    meter = db.Column(db.String(60), nullable=False)
    source_event_id = db.Column(db.String(120), nullable=False)
    hits = db.Column(db.Integer, nullable=False, default=1)
    recorded_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, index=True
    )
    actor_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        db.UniqueConstraint(
            "organization_id", "meter", "source_event_id",
            name="uq_usage_ledger_dedupe",
        ),
        db.CheckConstraint("hits > 0", name="ck_usage_ledger_hits"),
    )
