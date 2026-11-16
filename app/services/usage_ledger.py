"""Usage ledger service.

The ledger counts tenant-scoped business events (envelope prepared,
document ingested, stamp approved, verification success). Every entry
carries a ``source_event_id`` so a duplicate call — a retried request,
a replayed event, a worker that lost its ack and tried again — never
double-counts.

Public API:

* ``record(organization_id, meter, source_event_id, *, actor_id=None,
  hits=1, recorded_at=None)`` — idempotent insert. Returns ``True`` if
  a new row landed, ``False`` if the entry was already present.
* ``usage_for(organization_id, meter, *, since, until)`` — aggregate
  hit count for the window.
* ``current_period_usage(organization_id, meter, period)`` — rolling
  window: ``"day"``, ``"month"``, ``"year"``.

Known meters are enumerated in :data:`METERS` so the service rejects
typos at write time; callers add new meters there before using them.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.extensions import db
from app.models.usage_ledger import UsageLedgerEntry

METERS = frozenset(
    {
        "envelope.prepared",
        "envelope.finalized",
        "document.ingested",
        "document.bulk_ingested",
        "stamp.approved",
        "stamp.issued",
        "verification.success",
        "verification.failure",
    }
)

VALID_PERIODS = frozenset({"day", "month", "year"})


class UsageError(ValueError):
    """Raised for unknown meters or invalid periods."""


@dataclass(frozen=True)
class UsageWindow:
    start: datetime
    end: datetime


def record(
    organization_id: int,
    meter: str,
    source_event_id: str,
    *,
    actor_id: Optional[int] = None,
    hits: int = 1,
    recorded_at: Optional[datetime] = None,
) -> bool:
    if meter not in METERS:
        raise UsageError(f"unknown_meter:{meter}")
    if not isinstance(source_event_id, str) or not 1 <= len(source_event_id) <= 120:
        raise UsageError("source_event_id_invalid")
    if not isinstance(hits, int) or hits < 1:
        raise UsageError("hits_invalid")
    stmt = (
        pg_insert(UsageLedgerEntry)
        .values(
            organization_id=organization_id,
            meter=meter,
            source_event_id=source_event_id,
            hits=hits,
            recorded_at=recorded_at or datetime.utcnow(),
            actor_id=actor_id,
        )
        .on_conflict_do_nothing(
            index_elements=["organization_id", "meter", "source_event_id"]
        )
        .returning(UsageLedgerEntry.id)
    )
    result = db.session.execute(stmt).scalar_one_or_none()
    return result is not None


def usage_for(
    organization_id: int,
    meter: str,
    *,
    since: datetime,
    until: datetime,
) -> int:
    if meter not in METERS:
        raise UsageError(f"unknown_meter:{meter}")
    row = db.session.execute(
        db.select(func.coalesce(func.sum(UsageLedgerEntry.hits), 0)).where(
            UsageLedgerEntry.organization_id == organization_id,
            UsageLedgerEntry.meter == meter,
            UsageLedgerEntry.recorded_at >= since,
            UsageLedgerEntry.recorded_at < until,
        )
    ).scalar_one()
    return int(row or 0)


def _period_window(period: str, moment: datetime) -> UsageWindow:
    if period not in VALID_PERIODS:
        raise UsageError(f"unknown_period:{period}")
    if period == "day":
        start = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    elif period == "month":
        start = moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
    else:  # year
        start = moment.replace(
            month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        end = start.replace(year=start.year + 1)
    return UsageWindow(start=start, end=end)


def current_period_usage(
    organization_id: int, meter: str, period: str = "month"
) -> int:
    window = _period_window(period, datetime.utcnow())
    return usage_for(
        organization_id, meter, since=window.start, until=window.end
    )


def summary(
    organization_id: int, *, meters: Optional[Iterable[str]] = None,
    period: str = "month",
) -> dict[str, int]:
    """Return ``{meter: current-period hit count}`` for every known meter."""
    watched = list(meters) if meters else sorted(METERS)
    for m in watched:
        if m not in METERS:
            raise UsageError(f"unknown_meter:{m}")
    return {
        meter: current_period_usage(organization_id, meter, period)
        for meter in watched
    }
