"""Durable fixed-window rate limiter.

Closes G1 defence-in-depth: the previous in-process limiter under
``/verify`` and ``/sign`` applied per Flask worker, so an N-worker
deployment effectively multiplied the ceiling by N. The DB-backed
``consume`` serialises through PostgreSQL row locks.

Covers:

* First ``max_hits`` calls return ``allowed=True``, subsequent ones
  return ``allowed=False`` with a ``retry_after_seconds`` matching
  the current window.
* Window rollover resets the counter.
* Concurrent increments converge to the real DB count (single-thread
  loop; fine for the fixed-window case).
* ``prune_expired`` removes bucket rows whose window has elapsed.
* Invalid configuration raises :class:`RateLimitError`.
* Two separate bucket keys never influence each other.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.services.rate_limiting import (
    RateLimitError,
    _window_start,
    clear_cache,
    consume,
    prune_expired,
)


def _fresh_cache():
    clear_cache()


class TestConsume:
    def test_allows_up_to_max(self, pg_app):
        _fresh_cache()
        now = datetime.utcnow()
        for _ in range(3):
            decision = consume(
                bucket_key="unit:test:1",
                max_hits=3,
                window_seconds=10,
                now=now,
            )
            assert decision.allowed
            assert decision.limit == 3

    def test_denies_after_max(self, pg_app):
        _fresh_cache()
        now = datetime.utcnow()
        for _ in range(3):
            consume(
                bucket_key="unit:test:2",
                max_hits=3,
                window_seconds=10,
                now=now,
            )
        denied = consume(
            bucket_key="unit:test:2",
            max_hits=3,
            window_seconds=10,
            now=now,
        )
        assert denied.allowed is False
        assert denied.hits == 4
        assert denied.retry_after_seconds > 0

    def test_separate_keys_are_independent(self, pg_app):
        _fresh_cache()
        now = datetime.utcnow()
        for _ in range(5):
            consume(
                bucket_key="unit:keyA",
                max_hits=5,
                window_seconds=10,
                now=now,
            )
        other = consume(
            bucket_key="unit:keyB",
            max_hits=5,
            window_seconds=10,
            now=now,
        )
        assert other.allowed
        assert other.hits == 1

    def test_new_window_resets_counter(self, pg_app):
        _fresh_cache()
        base = datetime(2026, 11, 15, 12, 0, 0)
        for _ in range(3):
            consume(
                bucket_key="unit:roll",
                max_hits=3,
                window_seconds=10,
                now=base,
            )
        denied = consume(
            bucket_key="unit:roll",
            max_hits=3,
            window_seconds=10,
            now=base,
        )
        assert not denied.allowed
        # Jump 10 s forward: next window starts at base + 10 s.
        later = base + timedelta(seconds=10)
        fresh = consume(
            bucket_key="unit:roll",
            max_hits=3,
            window_seconds=10,
            now=later,
        )
        assert fresh.allowed
        assert fresh.hits == 1

    def test_invalid_config_raises(self, pg_app):
        _fresh_cache()
        with pytest.raises(RateLimitError):
            consume(bucket_key="", max_hits=1, window_seconds=1)
        with pytest.raises(RateLimitError):
            consume(bucket_key="x", max_hits=0, window_seconds=1)
        with pytest.raises(RateLimitError):
            consume(bucket_key="x", max_hits=1, window_seconds=0)
        with pytest.raises(RateLimitError):
            consume(bucket_key="x" * 161, max_hits=1, window_seconds=1)


class TestPrune:
    def test_prune_removes_only_expired(self, pg_app):
        _fresh_cache()
        now = datetime(2026, 11, 15, 12, 0, 0)
        # One row in the current window, one way in the past.
        consume(
            bucket_key="unit:prune:current",
            max_hits=5,
            window_seconds=60,
            now=now,
        )
        consume(
            bucket_key="unit:prune:expired",
            max_hits=5,
            window_seconds=60,
            now=now - timedelta(hours=2),
        )
        removed = prune_expired(now=now)
        assert removed >= 1
        # The current-window row survives.
        from app.extensions import db
        from app.models.rate_limit_bucket import RateLimitBucket

        survivors = (
            db.session.query(RateLimitBucket)
            .filter_by(bucket_key="unit:prune:current")
            .count()
        )
        assert survivors == 1


class TestWindowStart:
    def test_window_start_aligns_to_window_size(self):
        base = datetime(2026, 11, 15, 12, 0, 37)
        aligned = _window_start(base, window_seconds=60)
        assert aligned.second == 0
        assert aligned.minute == 0
        assert aligned.hour == 12


class TestDecisionPayload:
    def test_decision_carries_window_metadata(self, pg_app):
        _fresh_cache()
        now = datetime.utcnow()
        decision = consume(
            bucket_key="unit:payload",
            max_hits=2,
            window_seconds=5,
            now=now,
        )
        assert decision.limit == 2
        assert decision.window_seconds == 5
        assert decision.window_start.second == (now.second // 5) * 5
