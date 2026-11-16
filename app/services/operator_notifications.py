"""Service layer for in-app operator notifications (Phase W1).

Callers use :func:`publish` to emit a notification to one specific
operator. The service does not know about transport — delivery is
by polling via the ``/api/notifications`` surface — so writers
compose cleanly inside the same transaction as the business event
they notify about.
"""
from __future__ import annotations

from datetime import datetime

from app.extensions import db
from app.models.operator_notification import OperatorNotification


class NotificationError(ValueError):
    """Raised when a caller tries to publish an invalid notification."""


def publish(
    *,
    organization_id: int,
    recipient_user_id: int,
    kind: str,
    subject_type: str,
    subject_id: int | None,
    summary: str,
) -> OperatorNotification:
    """Insert one notification row for a recipient operator."""
    if not isinstance(organization_id, int) or organization_id <= 0:
        raise NotificationError("organization_id_invalid")
    if not isinstance(recipient_user_id, int) or recipient_user_id <= 0:
        raise NotificationError("recipient_user_id_invalid")
    if not isinstance(kind, str) or not kind.strip() or len(kind) > 60:
        raise NotificationError("kind_invalid")
    if not isinstance(subject_type, str) or not subject_type.strip() or len(subject_type) > 60:
        raise NotificationError("subject_type_invalid")
    if subject_id is not None and not isinstance(subject_id, int):
        raise NotificationError("subject_id_invalid")
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 400:
        raise NotificationError("summary_invalid")
    row = OperatorNotification(
        organization_id=organization_id,
        recipient_user_id=recipient_user_id,
        kind=kind,
        subject_type=subject_type,
        subject_id=subject_id,
        summary=summary,
    )
    db.session.add(row)
    db.session.flush()
    return row


def list_for(
    *,
    recipient_user_id: int,
    organization_id: int,
    unread_only: bool = False,
    limit: int = 100,
) -> list[OperatorNotification]:
    """Return up to ``limit`` notifications for an operator."""
    query = OperatorNotification.query.filter_by(
        recipient_user_id=recipient_user_id,
        organization_id=organization_id,
    )
    if unread_only:
        query = query.filter(OperatorNotification.read_at.is_(None))
    return (
        query.order_by(OperatorNotification.id.desc())
        .limit(min(max(limit, 1), 500))
        .all()
    )


def count_unread(
    *, recipient_user_id: int, organization_id: int
) -> int:
    return (
        OperatorNotification.query.filter_by(
            recipient_user_id=recipient_user_id,
            organization_id=organization_id,
        )
        .filter(OperatorNotification.read_at.is_(None))
        .count()
    )


def mark_read(
    *,
    notification_id: int,
    recipient_user_id: int,
    organization_id: int,
) -> OperatorNotification | None:
    row = OperatorNotification.query.filter_by(
        id=notification_id,
        recipient_user_id=recipient_user_id,
        organization_id=organization_id,
    ).first()
    if row is None:
        return None
    if row.read_at is None:
        row.read_at = datetime.utcnow()
        db.session.flush()
    return row


def mark_all_read(
    *, recipient_user_id: int, organization_id: int
) -> int:
    now = datetime.utcnow()
    updated = (
        OperatorNotification.query.filter_by(
            recipient_user_id=recipient_user_id,
            organization_id=organization_id,
        )
        .filter(OperatorNotification.read_at.is_(None))
        .update({OperatorNotification.read_at: now}, synchronize_session=False)
    )
    db.session.flush()
    return updated
