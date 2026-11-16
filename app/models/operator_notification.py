"""In-app operator notifications (Phase W1).

A lightweight per-operator feed that complements the webhook
subscription surface. Writers emit a row for one specific
operator (``recipient_user_id``); the operator pulls unread rows
via ``GET /api/notifications`` and marks them read.

Rows are tenant-scoped via RLS and append-only — the service
never mutates ``kind`` / ``summary`` / ``subject_*`` after the
initial insert.
"""
from datetime import datetime

from app.extensions import db


class OperatorNotification(db.Model):
    __tablename__ = "operator_notifications"

    id = db.Column(db.BigInteger, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    recipient_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    kind = db.Column(db.String(60), nullable=False, index=True)
    subject_type = db.Column(db.String(60), nullable=False)
    subject_id = db.Column(db.BigInteger, nullable=True)
    summary = db.Column(db.String(400), nullable=False)
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, index=True
    )
    read_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.CheckConstraint(
            "char_length(kind) >= 1",
            name="ck_operator_notification_kind_present",
        ),
        db.CheckConstraint(
            "char_length(summary) >= 1",
            name="ck_operator_notification_summary_present",
        ),
        db.Index(
            "ix_operator_notifications_recipient_unread",
            "recipient_user_id",
            "read_at",
        ),
    )
