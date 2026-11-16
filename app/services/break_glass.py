"""Break-glass access service (K3).

Public entry points:

* ``grant(operator_id, granted_by_id, scope, reason, *,
  ttl_minutes=None, organization_id=None)`` — mints a grant plus a
  short-lived JWT access token. Refuses self-grants.
* ``revoke(grant_id, revoked_by_id, reason)`` — ends the grant;
  subsequent token refreshes refuse.
* ``check(operator_id, scope)`` — called by decorators / middleware;
  returns the active grant or raises ``BreakGlassError``.
* ``exercise(grant)`` — records a use. Called from inside a request
  handler that has already verified the grant.

Every grant / revocation / use emits a chained SecurityEvent so the
operator's break-glass behaviour is auditable after the fact.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from flask import current_app
from flask_jwt_extended import create_access_token

from app.extensions import db
from app.models.break_glass_grant import BreakGlassGrant
from app.models.event_delivery import SecurityEvent
from app.models.user import User


class BreakGlassError(RuntimeError):
    """Policy or state failure in the break-glass service."""


@dataclass(frozen=True)
class BreakGlassIssue:
    grant_id: int
    access_token: str
    expires_at: datetime


def _ttl(minutes: Optional[int]) -> timedelta:
    if minutes is None:
        minutes = int(current_app.config.get("BREAK_GLASS_TTL_MINUTES") or 30)
    if minutes <= 0 or minutes > 240:
        raise BreakGlassError("ttl_out_of_range")
    return timedelta(minutes=minutes)


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
            resource_type="break_glass_grant",
            resource_id=resource_id,
            outcome=outcome,
            correlation_id=uuid.uuid4().hex,
        )
    )


def grant(
    *,
    operator_id: int,
    granted_by_id: int,
    scope: str,
    reason: str,
    ttl_minutes: Optional[int] = None,
    organization_id: Optional[int] = None,
) -> BreakGlassIssue:
    if operator_id == granted_by_id:
        raise BreakGlassError("self_grant_forbidden")
    if not isinstance(scope, str) or not 1 <= len(scope) <= 80:
        raise BreakGlassError("scope_invalid")
    if not isinstance(reason, str) or not 1 <= len(reason) <= 500:
        raise BreakGlassError("reason_required")
    operator = db.session.get(User, operator_id)
    grantor = db.session.get(User, granted_by_id)
    if operator is None or grantor is None:
        raise BreakGlassError("user_not_found")
    if not grantor.is_active:
        raise BreakGlassError("grantor_inactive")
    now = datetime.utcnow()
    delta = _ttl(ttl_minutes)
    expires_at = now + delta
    row = BreakGlassGrant(
        operator_id=operator_id,
        granted_by_id=granted_by_id,
        organization_id=organization_id,
        scope=scope,
        reason=reason,
        granted_at=now,
        expires_at=expires_at,
    )
    db.session.add(row)
    db.session.flush()
    _emit(
        actor_id=granted_by_id,
        organization_id=organization_id,
        action="break_glass.granted",
        resource_id=row.id,
        outcome="ok",
    )
    token = create_access_token(
        identity=str(operator_id),
        additional_claims={
            "break_glass_grant_id": row.id,
            "break_glass_scope": scope,
            "mfa_verified_at": int(time.time()),
        },
        expires_delta=delta,
    )
    return BreakGlassIssue(
        grant_id=row.id,
        access_token=token,
        expires_at=expires_at,
    )


def revoke(
    grant_id: int,
    *,
    revoked_by_id: int,
    reason: Optional[str] = None,
) -> BreakGlassGrant:
    row = db.session.get(BreakGlassGrant, grant_id)
    if row is None:
        raise BreakGlassError("grant_not_found")
    if row.revoked_at is not None:
        return row
    row.revoked_at = datetime.utcnow()
    row.revoked_by_id = revoked_by_id
    row.revoke_reason = reason
    _emit(
        actor_id=revoked_by_id,
        organization_id=row.organization_id,
        action="break_glass.revoked",
        resource_id=row.id,
        outcome="revoked",
    )
    return row


def check(operator_id: int, scope: str) -> BreakGlassGrant:
    """Return an unrevoked, unexpired grant for ``operator_id`` + ``scope``."""
    now = datetime.utcnow()
    row = (
        BreakGlassGrant.query.filter(
            BreakGlassGrant.operator_id == operator_id,
            BreakGlassGrant.scope == scope,
            BreakGlassGrant.revoked_at.is_(None),
            BreakGlassGrant.expires_at > now,
        )
        .order_by(BreakGlassGrant.granted_at.desc())
        .first()
    )
    if row is None:
        raise BreakGlassError("no_active_grant")
    return row


def exercise(grant: BreakGlassGrant, *, actor_id: int) -> None:
    """Record a successful use of ``grant``."""
    grant.use_count += 1
    grant.last_used_at = datetime.utcnow()
    _emit(
        actor_id=actor_id,
        organization_id=grant.organization_id,
        action="break_glass.used",
        resource_id=grant.id,
        outcome="ok",
    )
