"""Durable (DB-backed) fixed-window rate limiter.

Closes gap G1 defence-in-depth: the previous in-process limiter under
``/verify`` and ``/sign`` applied per-worker, so an N-worker
deployment effectively multiplied the configured ceiling by N.
``consume`` here serialises writes through PostgreSQL row-level locks
so the whole cluster converges to one rate per bucket.

The limiter is intentionally plain fixed-window — simpler than token
bucket, easier to reason about, more than enough for anti-abuse
rails in front of anonymous surfaces. Precision is 1 second.

Call sites use ``RateLimitDecision`` to decide 429-vs-200:

    decision = consume(
        bucket_key=f"verify:{client_fingerprint}",
        max_hits=10,
        window_seconds=60,
    )
    if not decision.allowed:
        return rate_limited_response(decision.retry_after_seconds)

A thread-safe in-process cache sits in front of the DB so routine
checks for a bucket within the current second cost one dict lookup.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.rate_limit_bucket import RateLimitBucket

_CACHE_LOCK = Lock()
_WINDOW_CACHE: dict[str, tuple[datetime, int]] = {}
_CACHE_LIMIT = 4096


class RateLimitError(RuntimeError):
    """Invalid arguments to :func:`consume`."""


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    hits: int
    limit: int
    window_seconds: int
    window_start: datetime
    retry_after_seconds: int


def _window_start(now: datetime, window_seconds: int) -> datetime:
    """Align ``now`` to the current window start.

    Naive datetimes are treated as UTC so a deployment running in a
    non-UTC timezone produces the same window boundaries as one in
    UTC. ``calendar.timegm`` converts a struct_time in UTC to an
    epoch without applying the local offset.
    """
    import calendar

    reference = (
        now if now.tzinfo is None else now.astimezone(tz=None).replace(tzinfo=None)
    )
    epoch_seconds = int(calendar.timegm(reference.utctimetuple()))
    floored = (epoch_seconds // window_seconds) * window_seconds
    return datetime.utcfromtimestamp(floored)


def consume(
    *,
    bucket_key: str,
    max_hits: int,
    window_seconds: int,
    now: datetime | None = None,
) -> RateLimitDecision:
    """Record one hit on ``bucket_key`` and return the decision.

    When ``hits > max_hits`` after increment the decision is denied.
    The ``retry_after_seconds`` field holds the seconds remaining in
    the current window so callers can surface a ``Retry-After`` header.
    """
    if (
        not isinstance(bucket_key, str)
        or not 1 <= len(bucket_key) <= 160
        or not isinstance(max_hits, int)
        or max_hits < 1
        or not isinstance(window_seconds, int)
        or window_seconds < 1
        or window_seconds > 86_400
    ):
        raise RateLimitError("invalid rate-limit configuration")
    moment = now or datetime.utcnow()
    window_start = _window_start(moment, window_seconds)

    # Fast path: a hit for the same bucket + window served in the
    # last second never needs to touch the DB.
    cache_key = f"{bucket_key}|{window_start.isoformat()}"
    cached_hits = 0
    with _CACHE_LOCK:
        cached = _WINDOW_CACHE.get(cache_key)
        if cached is not None:
            cached_hits = cached[1]
    # Still write-through so other workers see the bump and the cache
    # cannot silently decay under contention; the DB is authoritative.
    hits = _incr(bucket_key, window_start, window_seconds)
    with _CACHE_LOCK:
        _WINDOW_CACHE[cache_key] = (window_start, hits)
        if len(_WINDOW_CACHE) > _CACHE_LIMIT:
            # Evict the oldest half; cache is a convenience not a
            # security boundary.
            for key in list(_WINDOW_CACHE)[: _CACHE_LIMIT // 2]:
                _WINDOW_CACHE.pop(key, None)
    allowed = hits <= max_hits
    window_end = window_start + timedelta(seconds=window_seconds)
    retry_after = max(0, int((window_end - moment).total_seconds())) if not allowed else 0
    return RateLimitDecision(
        allowed=allowed,
        hits=hits,
        limit=max_hits,
        window_seconds=window_seconds,
        window_start=window_start,
        retry_after_seconds=retry_after,
    )


def _incr(
    bucket_key: str, window_start: datetime, window_seconds: int
) -> int:
    """Insert-or-update the bucket row and return the new ``hits``.

    Uses ``INSERT ... ON CONFLICT DO UPDATE`` so the lock scope is one
    row; concurrent workers never block each other on the key index.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = (
        pg_insert(RateLimitBucket.__table__)
        .values(
            bucket_key=bucket_key,
            window_start=window_start,
            window_seconds=window_seconds,
            hits=1,
            created_at=datetime.utcnow(),
        )
        .on_conflict_do_update(
            constraint="uq_rate_limit_bucket_key_window",
            set_={"hits": RateLimitBucket.__table__.c.hits + 1},
        )
        .returning(RateLimitBucket.__table__.c.hits)
    )
    try:
        result = db.session.execute(stmt)
        db.session.commit()
    except IntegrityError:
        # Row was created by another worker between our insert attempt
        # and the ON CONFLICT path; retry once as a simple increment.
        db.session.rollback()
        updated = (
            RateLimitBucket.query.filter_by(
                bucket_key=bucket_key, window_start=window_start
            )
            .with_for_update()
            .first()
        )
        if updated is None:
            raise
        updated.hits += 1
        db.session.commit()
        return int(updated.hits)
    return int(result.scalar_one())


def prune_expired(now: datetime | None = None) -> int:
    """Remove bucket rows whose window has elapsed.

    Returns the number of deleted rows. Operators call this from the
    retention CLI; ``consume`` never deletes.
    """
    moment = now or datetime.utcnow()
    from sqlalchemy import func

    cutoff_expression = (
        RateLimitBucket.window_start
        + func.make_interval(0, 0, 0, 0, 0, 0, RateLimitBucket.window_seconds)
    )
    removed = (
        RateLimitBucket.query.filter(cutoff_expression < moment).delete(
            synchronize_session=False
        )
    )
    db.session.commit()
    return int(removed)


def clear_cache() -> None:
    """Drop the in-process window cache (test helper)."""
    with _CACHE_LOCK:
        _WINDOW_CACHE.clear()
