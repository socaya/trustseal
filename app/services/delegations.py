"""Time-bound, scope-limited delegation.

Delegations let one user temporarily exercise another's authority for
a named scope (``stamp.approve``, ``envelope.finalize``, ...). They
are not role grants — the delegate's permanent permissions do not
change. Every grant / revoke / use emits a ``SecurityEvent``.

Public API:

* ``grant(delegator_id, delegate_id, scope, *, starts_at, expires_at,
  granted_by_id, resource_type=None, resource_id=None, reason=None)``
* ``revoke(delegation_id, *, revoked_by_id, reason=None)``
* ``active_for(delegate_id, scope, *, resource_type=None,
  resource_id=None, now=None)`` — return the matching active
  delegations the user can exercise right now. Caller decides what
  to do with them.
* ``effective_delegators(delegate_id, scope, *, resource_type=None,
  resource_id=None)`` — convenience wrapper returning just the
  delegator ids.

Policy:

* A delegate can never delegate to themselves (``delegator_id ==
  delegate_id`` raises).
* The validity window must be in the future (``expires_at > now``)
  and non-empty (``expires_at > starts_at``).
* Scope ``"*"`` is accepted and matches every scope lookup. Used for
  short out-of-office transfers.
* ``resource_type`` + ``resource_id`` narrow the delegation. If a
  delegation is tenant-wide (both NULL) it matches any lookup that
  specifies a resource.
* Revoked delegations are inert regardless of window.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import and_, or_

from app.extensions import db
from app.models.delegation import Delegation
from app.models.event_delivery import SecurityEvent
from app.models.user import User


class DelegationError(Exception):
    """Policy violation in the delegation service."""


# ------------------------------------------------------------- grant


def grant(
    *,
    delegator_id: int,
    delegate_id: int,
    scope: str,
    starts_at: datetime,
    expires_at: datetime,
    granted_by_id: int,
    organization_id: Optional[int] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    reason: Optional[str] = None,
) -> Delegation:
    if delegator_id == delegate_id:
        raise DelegationError("self_delegation_forbidden")
    if not isinstance(scope, str) or not 1 <= len(scope) <= 80:
        raise DelegationError("scope_invalid")
    now = datetime.utcnow()
    if expires_at <= now:
        raise DelegationError("expiry_in_past")
    if expires_at <= starts_at:
        raise DelegationError("empty_window")
    delegator = db.session.get(User, delegator_id)
    delegate = db.session.get(User, delegate_id)
    if delegator is None or delegate is None:
        raise DelegationError("user_not_found")
    if delegator.organization_id != delegate.organization_id:
        raise DelegationError("cross_organization_forbidden")
    resolved_org = organization_id or delegator.organization_id
    row = Delegation(
        organization_id=resolved_org,
        delegator_id=delegator_id,
        delegate_id=delegate_id,
        scope=scope,
        resource_type=resource_type,
        resource_id=(int(resource_id) if resource_id is not None else None),
        reason=reason,
        starts_at=starts_at,
        expires_at=expires_at,
        granted_at=now,
        granted_by_id=granted_by_id,
    )
    db.session.add(row)
    db.session.flush()
    _emit(
        actor_id=granted_by_id,
        organization_id=resolved_org,
        action="delegation.granted",
        resource_id=row.id,
        outcome="ok",
    )
    return row


# ------------------------------------------------------------- revoke


def revoke(
    delegation_id: int,
    *,
    revoked_by_id: int,
    reason: Optional[str] = None,
) -> Delegation:
    row = db.session.get(Delegation, delegation_id)
    if row is None:
        raise DelegationError("delegation_not_found")
    if row.revoked_at is not None:
        return row
    row.revoked_at = datetime.utcnow()
    row.revoked_by_id = revoked_by_id
    row.revoke_reason = reason
    _emit(
        actor_id=revoked_by_id,
        organization_id=row.organization_id,
        action="delegation.revoked",
        resource_id=row.id,
        outcome="revoked",
    )
    return row


# ------------------------------------------------------------- query


def active_for(
    delegate_id: int,
    scope: str,
    *,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    now: Optional[datetime] = None,
) -> list[Delegation]:
    """Return active delegations the user may exercise right now.

    A delegation matches when:

    * ``delegate_id`` matches,
    * window contains ``now`` (``starts_at <= now < expires_at``),
    * ``revoked_at`` is NULL,
    * ``scope`` equals the stored scope OR the stored scope is ``*``,
    * resource qualifiers are either absent on the delegation or
      exactly match the lookup.
    """
    moment = now or datetime.utcnow()
    scope_match = Delegation.scope.in_([scope, "*"])
    resource_match = or_(
        and_(
            Delegation.resource_type.is_(None),
            Delegation.resource_id.is_(None),
        ),
        and_(
            Delegation.resource_type == resource_type,
            Delegation.resource_id == (int(resource_id) if resource_id is not None else None),
        ),
    )
    query = Delegation.query.filter(
        Delegation.delegate_id == delegate_id,
        Delegation.revoked_at.is_(None),
        Delegation.starts_at <= moment,
        Delegation.expires_at > moment,
        scope_match,
        resource_match,
    )
    return query.order_by(Delegation.granted_at.asc()).all()


def effective_delegators(
    delegate_id: int,
    scope: str,
    *,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    now: Optional[datetime] = None,
) -> list[int]:
    """IDs of users whose authority ``delegate_id`` currently holds."""
    rows = active_for(
        delegate_id,
        scope,
        resource_type=resource_type,
        resource_id=resource_id,
        now=now,
    )
    return [r.delegator_id for r in rows]


def record_use(
    delegation: Delegation, *, actor_id: int, action: str
) -> None:
    """Audit the delegate using ``delegation`` to perform ``action``."""
    _emit(
        actor_id=actor_id,
        organization_id=delegation.organization_id,
        action=f"delegation.used.{action}",
        resource_id=delegation.id,
        outcome="ok",
    )


# ----------------------------------------------------------- audit


def _emit(
    *,
    actor_id: int,
    organization_id: Optional[int],
    action: str,
    resource_id: int,
    outcome: str,
) -> None:
    db.session.add(
        SecurityEvent(
            organization_id=organization_id,
            actor_id=actor_id,
            action=action,
            resource_type="delegation",
            resource_id=resource_id,
            outcome=outcome,
            correlation_id=uuid.uuid4().hex,
        )
    )
