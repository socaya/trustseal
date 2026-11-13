"""Commit business mutations, security events and outbox messages together.

Call enqueue() BEFORE the caller's db.session.commit(). It never commits.
The worker is at-least-once, not exactly-once; consumers must deduplicate.
"""
import json
import uuid
from datetime import datetime, timedelta
from sqlalchemy import and_, or_

from app.extensions import db
from app.models.event_delivery import SecurityEvent, OutboxEvent

MAX_ATTEMPTS = 8
LEASE_SECONDS = 120


def enqueue(*, event_type, aggregate_type, aggregate_id, organization_id,
            actor_id, action, idempotency_key, correlation_id=None):
    if not idempotency_key or len(idempotency_key) > 128:
        raise ValueError("A stable idempotency key is required")
    if type(aggregate_id) is not int:
        raise ValueError("An integer aggregate ID is required")
    if not event_type or not aggregate_type or not action:
        raise ValueError("Event classification required")
    correlation_id = correlation_id or uuid.uuid4().hex
    event = SecurityEvent(
        organization_id=organization_id, actor_id=actor_id, action=action,
        resource_type=aggregate_type, resource_id=aggregate_id,
        outcome="success", correlation_id=correlation_id,
    )
    message = OutboxEvent(
        event_type=event_type, aggregate_type=aggregate_type,
        aggregate_id=aggregate_id, organization_id=organization_id,
        payload={"aggregate_id": aggregate_id, "correlation_id": correlation_id},
        idempotency_key=idempotency_key, state="pending", attempts=0,
        next_attempt_at=datetime.utcnow(),
    )
    db.session.add_all([event, message])
    return message


def claim_next():
    """Claim a due event, recovering expired leases safely.

    Each claim increments attempts. If a crashed worker exhausted the retry
    budget, the lease is marked dead without repeating its side effects.
    """
    now = datetime.utcnow()
    query = db.session.query(OutboxEvent).filter(
        or_(
            and_(OutboxEvent.state == "pending", OutboxEvent.next_attempt_at <= now),
            and_(OutboxEvent.state == "processing", OutboxEvent.locked_until <= now),
        )
    ).order_by(OutboxEvent.id).with_for_update(skip_locked=True)
    while True:
        item = query.first()
        if item is None:
            db.session.commit()
            return None
        if item.attempts >= MAX_ATTEMPTS:
            item.state = "dead"
            item.locked_until = None
            item.last_error = "Retry budget exhausted after lease expiry"
            db.session.commit()
            continue
        item.state = "processing"
        item.attempts += 1
        # Microsecond uniqueness across claims is not a complete fencing
        # token. External side effects still require consumer idempotency.
        item.locked_until = now + timedelta(seconds=LEASE_SECONDS)
        db.session.commit()
        return item.id, item.locked_until


def renew_lease(event_id, lease_until):
    """Extend a lease held by this worker before executing a long handler."""
    now = datetime.utcnow()
    item = db.session.query(OutboxEvent).filter_by(
        id=event_id, state="processing", locked_until=lease_until
    ).with_for_update().first()
    if item is None or item.locked_until <= now:
        db.session.rollback()
        return None
    item.locked_until = now + timedelta(seconds=LEASE_SECONDS)
    db.session.commit()
    return item.locked_until


def finish(event_id, lease_until, *, success, error=None):
    """A stale worker must not acknowledge a newer worker's lease."""
    item = db.session.query(OutboxEvent).filter_by(
        id=event_id, state="processing", locked_until=lease_until
    ).with_for_update().first()
    if item is None:
        db.session.rollback()
        return False
    # If lease expired, do not acknowledge; recovery owns the next attempt.
    if item.locked_until <= datetime.utcnow():
        db.session.rollback()
        return False
    item.locked_until = None
    if success:
        item.state = "completed"
        item.completed_at = datetime.utcnow()
        item.last_error = None
    else:
        item.last_error = (str(error or "Worker failure"))[:200]
        if item.attempts >= MAX_ATTEMPTS:
            item.state = "dead"
        else:
            item.state = "pending"
            seconds = min(3600, 2 ** min(item.attempts, 11))
            item.next_attempt_at = datetime.utcnow() + timedelta(seconds=seconds)
    db.session.commit()
    return True


def deliver_one(handlers):
    """Dispatch only explicitly registered, trusted handlers by event type."""
    claim = claim_next()
    if claim is None:
        return False
    event_id, lease_until = claim
    item = db.session.get(OutboxEvent, event_id)
    handler = handlers.get(item.event_type)
    if handler is None:
        finish(event_id, lease_until, success=False, error="No registered handler")
        return True
    try:
        handler(dict(item.payload), item.idempotency_key)
    except Exception as exc:
        db.session.rollback()
        finish(event_id, lease_until, success=False, error=type(exc).__name__)
    else:
        finish(event_id, lease_until, success=True)
    return True
