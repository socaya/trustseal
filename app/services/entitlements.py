"""Plan entitlement enforcement.

A tenant's active subscription points at a ``SubscriptionPlan``. If
a ``PlanEntitlement`` row exists for the plan + meter, the current
usage must be below ``hit_limit`` or the mutation is refused.

Public API:

* ``check(organization_id, meter, *, now=None)`` — returns the
  entitlement decision. Raises :class:`EntitlementExceeded` when
  usage has met or exceeded the limit.
* ``decision(...)`` — same check but returns a structured
  ``Decision`` object (allowed / used / limit / period) without
  raising, useful for callers that want to surface the number before
  taking the action.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from app.extensions import db
from app.models.organization import Organization
from app.models.plan_entitlement import PlanEntitlement
from app.models.subscription import Subscription
from app.services import usage_ledger


class EntitlementExceeded(RuntimeError):
    """The tenant has met or exceeded the metered plan limit."""

    def __init__(self, *, meter: str, period: str, used: int, limit: int):
        super().__init__(f"entitlement_exceeded:{meter}:{used}/{limit}:{period}")
        self.meter = meter
        self.period = period
        self.used = used
        self.limit = limit


@dataclass(frozen=True)
class Decision:
    allowed: bool
    meter: str
    period: str
    used: int
    limit: Optional[int]

    def ensure(self) -> None:
        if not self.allowed:
            raise EntitlementExceeded(
                meter=self.meter,
                period=self.period,
                used=self.used,
                limit=self.limit or 0,
            )


def _active_plan_id(organization_id: int) -> Optional[int]:
    """Return the plan id for the org's current subscription, if any."""
    org = db.session.get(Organization, organization_id)
    if org is None:
        return None
    sub = db.session.execute(
        select(Subscription)
        .where(Subscription.id == org.subscription_id)
        .where(Subscription.is_active.is_(True))
    ).scalar_one_or_none() if getattr(org, "subscription_id", None) else None
    if sub is None:
        return None
    return sub.plan_id


def decision(
    organization_id: int,
    meter: str,
    *,
    now: Optional[datetime] = None,
) -> Decision:
    """Return the current entitlement decision without raising."""
    plan_id = _active_plan_id(organization_id)
    if plan_id is None:
        # No active subscription → unmetered (no enforcement until
        # commercial onboarding completes). Audit remains intact via
        # the usage ledger.
        return Decision(
            allowed=True, meter=meter, period="month", used=0, limit=None
        )
    row = db.session.execute(
        select(PlanEntitlement).where(
            PlanEntitlement.plan_id == plan_id,
            PlanEntitlement.meter == meter,
        )
    ).scalar_one_or_none()
    if row is None:
        return Decision(
            allowed=True, meter=meter, period="month", used=0, limit=None
        )
    used = usage_ledger.current_period_usage(
        organization_id, meter, period=row.period
    )
    return Decision(
        allowed=used < row.hit_limit,
        meter=meter,
        period=row.period,
        used=used,
        limit=int(row.hit_limit),
    )


def check(
    organization_id: int,
    meter: str,
    *,
    now: Optional[datetime] = None,
) -> Decision:
    """Shortcut: run :func:`decision` and raise if denied."""
    d = decision(organization_id, meter, now=now)
    d.ensure()
    return d
