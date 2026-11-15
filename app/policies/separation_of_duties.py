"""Separation-of-duties enforcement.

Several trust-critical actions must not be executed by the same user
who initiated them. Approving a stamp you yourself requested, or
granting yourself a privileged role, defeats the four-eyes principle
these controls exist to uphold.

This module centralises the check so individual handlers don't drift
into inconsistent rules:

* :func:`assert_distinct(actor_id, *conflicting_ids)` raises
  :class:`SeparationOfDutiesViolation` when any of the conflicting
  ids equals ``actor_id``. Call it from any handler that needs the
  rule.
* :func:`enforce(actor_id, record, *, fields)` reads conflicting ids
  from attributes on ``record`` (``created_by_id``, ``custodian_id``,
  etc.) and applies the same check.
* A ``SecurityEvent`` row is emitted on every violation so the audit
  chain captures the attempt even though the HTTP response is a 403.

Routes integrate the policy either by calling the helpers directly or
by using the :func:`require_separation_of_duties` decorator, which is
useful for admin RBAC mutations where the record lives in the request
body.
"""
from __future__ import annotations

import uuid
from functools import wraps
from typing import Callable, Iterable, Optional

from flask import abort, jsonify

from app.extensions import db
from app.models.event_delivery import SecurityEvent


class SeparationOfDutiesViolation(Exception):
    """Raised when the actor is also the requester / subject of the action."""

    def __init__(self, *, action: str, conflict_role: str, actor_id: int):
        super().__init__(
            f"separation_of_duties:{action}:actor_is_{conflict_role}"
        )
        self.action = action
        self.conflict_role = conflict_role
        self.actor_id = actor_id


def assert_distinct(
    actor_id: int,
    *conflicting_ids: tuple[Optional[int], str],
    action: str,
    organization_id: Optional[int] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
) -> None:
    """Fail-closed when ``actor_id`` matches any conflicting id.

    ``conflicting_ids`` is a list of ``(id, role_label)`` tuples. The
    ``role_label`` names the role the id plays (``"requester"``,
    ``"custodian"``, ``"subject"``) and surfaces in the raised
    exception + emitted security event.
    """
    for candidate, role in conflicting_ids:
        if candidate is not None and int(candidate) == int(actor_id):
            _emit_denial(
                actor_id=actor_id,
                action=action,
                conflict_role=role,
                organization_id=organization_id,
                resource_type=resource_type,
                resource_id=resource_id,
            )
            raise SeparationOfDutiesViolation(
                action=action, conflict_role=role, actor_id=actor_id
            )


def enforce(
    actor_id: int,
    record,
    *,
    action: str,
    fields: Iterable[str] = ("created_by_id", "requested_by_id", "custodian_id"),
    organization_id: Optional[int] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
) -> None:
    """Apply the SoD check by reading ``fields`` off ``record``.

    Missing attributes are ignored so the same helper works on heterogeneous
    records. The ``resource_type`` / ``resource_id`` default to the
    record's own ``__tablename__`` and ``id`` if not provided.
    """
    resolved_type = resource_type or getattr(
        getattr(record, "__table__", None), "name", None
    ) or type(record).__name__.lower()
    resolved_id = resource_id if resource_id is not None else getattr(record, "id", None)
    resolved_org = (
        organization_id
        if organization_id is not None
        else getattr(record, "organization_id", None)
    )
    conflicts = []
    for name in fields:
        value = getattr(record, name, None)
        if value is not None:
            conflicts.append((int(value), name))
    assert_distinct(
        actor_id,
        *conflicts,
        action=action,
        organization_id=resolved_org,
        resource_type=resolved_type,
        resource_id=resolved_id,
    )


def require_separation_of_duties(
    action: str,
    get_record: Callable,
    fields: Iterable[str] = ("created_by_id", "requested_by_id", "custodian_id"),
) -> Callable:
    """Decorator that reads a record via ``get_record(**kwargs)`` and enforces SoD.

    The decorated handler receives the same kwargs. If the policy
    denies, the response is 403 with a machine-readable body so
    clients can present a useful error.
    """

    def _decorator(func: Callable) -> Callable:
        @wraps(func)
        def _wrapper(*args, **kwargs):
            from app.services.token_security import active_token_user

            actor = active_token_user()
            if actor is None or not actor.is_active:
                abort(401)
            record = get_record(**kwargs)
            if record is None:
                abort(404)
            try:
                enforce(actor.id, record, action=action, fields=fields)
            except SeparationOfDutiesViolation as exc:
                db.session.commit()  # persist the security event
                return (
                    jsonify(
                        error=str(exc),
                        action=exc.action,
                        conflict_role=exc.conflict_role,
                        type="https://trustseal.dev/problems/separation-of-duties",
                    ),
                    403,
                )
            return func(*args, **kwargs)

        return _wrapper

    return _decorator


def _emit_denial(
    *,
    actor_id: int,
    action: str,
    conflict_role: str,
    organization_id: Optional[int],
    resource_type: Optional[str],
    resource_id: Optional[int],
) -> None:
    event = SecurityEvent(
        organization_id=organization_id,
        actor_id=actor_id,
        action=f"separation_of_duties.{action}",
        resource_type=resource_type or "unknown",
        resource_id=(int(resource_id) if resource_id is not None else None),
        outcome="denied",
        correlation_id=uuid.uuid4().hex,
    )
    db.session.add(event)
