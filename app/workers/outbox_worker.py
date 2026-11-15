"""Outbox drain daemon.

Long-lived loop that claims and dispatches outbox events using the
HANDLERS dictionary in ``app/cli/outbox.py``. Design notes:

* Lease fencing is enforced by ``app.services.event_delivery.claim_next``;
  this worker is one of possibly many drainers.
* On an empty queue, back off exponentially between polls up to a cap so
  idle instances do not hammer the database.
* On SIGTERM / SIGINT / SIGHUP, finish the in-flight event, then exit
  cleanly with status 0. systemd / supervisor will restart on failure.
* Each tick runs inside a Flask ``app_context`` so SQLAlchemy sessions
  are scoped per iteration; a failure in one event does not leak state
  into the next.
* Metrics are emitted through the module-level structlog logger; no
  separate exporter is wired in this stage.

The module exposes :func:`run` so callers (tests, CLI) can drive the
loop without importing private symbols.
"""
from __future__ import annotations

import os
import signal
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Mapping

import structlog

log = structlog.get_logger("trustseal.worker.outbox")

_DEFAULT_IDLE_INITIAL = 0.25
_DEFAULT_IDLE_MAX = 5.0
_DEFAULT_ERROR_BACKOFF = 2.0
_DEFAULT_MAX_ITERATIONS: int | None = None


@dataclass
class WorkerStats:
    """Mutable counters used for both observability and tests."""

    processed: int = 0
    empty: int = 0
    errors: int = 0
    iterations: int = 0
    stopped_at: float | None = field(default=None)


class StopRequested(Exception):
    """Raised internally by signal handlers to break the loop cleanly."""


class OutboxWorker:
    """Reentrant worker. ``run()`` is not thread-safe per instance."""

    def __init__(
        self,
        app,
        *,
        handlers: Mapping[str, Callable],
        idle_initial: float = _DEFAULT_IDLE_INITIAL,
        idle_max: float = _DEFAULT_IDLE_MAX,
        error_backoff: float = _DEFAULT_ERROR_BACKOFF,
        max_iterations: int | None = _DEFAULT_MAX_ITERATIONS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if idle_initial <= 0 or idle_max <= 0 or error_backoff <= 0:
            raise ValueError("backoff parameters must be positive")
        if idle_max < idle_initial:
            raise ValueError("idle_max must be >= idle_initial")
        self._app = app
        self._handlers = handlers
        self._idle_initial = idle_initial
        self._idle_max = idle_max
        self._error_backoff = error_backoff
        self._max_iterations = max_iterations
        self._sleep = sleep
        self._stop_event = threading.Event()
        self.stats = WorkerStats()

    def request_stop(self) -> None:
        self._stop_event.set()

    def _install_signals(self) -> None:
        # Only install signal handlers when running on the main thread of the
        # main interpreter. Tests often run the worker on helper threads
        # where ``signal.signal`` is disallowed.
        if threading.current_thread() is not threading.main_thread():
            return
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            try:
                signal.signal(sig, lambda *_args: self.request_stop())
            except (ValueError, OSError):  # pragma: no cover - platform-specific
                pass

    def _tick(self) -> bool:
        """Run one event. Returns True if an event was processed, else False."""
        from app.services.event_delivery import deliver_one

        with self._app.app_context():
            try:
                return bool(deliver_one(self._handlers))
            except Exception as exc:
                self.stats.errors += 1
                log.exception("outbox_tick_failed", error=str(exc))
                return False

    def run(self) -> WorkerStats:
        """Drive the main loop. Returns the collected stats on exit."""
        self._install_signals()
        log.info(
            "outbox_worker_started",
            pid=os.getpid(),
            idle_initial=self._idle_initial,
            idle_max=self._idle_max,
        )
        idle_delay = self._idle_initial
        try:
            while not self._stop_event.is_set():
                self.stats.iterations += 1
                processed = self._tick()
                if processed:
                    self.stats.processed += 1
                    idle_delay = self._idle_initial
                else:
                    self.stats.empty += 1
                    # Only sleep when the queue is quiet; a busy queue never
                    # pauses. Use the stop_event so SIGTERM breaks the sleep
                    # immediately.
                    self._stop_event.wait(timeout=idle_delay)
                    idle_delay = min(self._idle_max, idle_delay * 2)
                if (
                    self._max_iterations is not None
                    and self.stats.iterations >= self._max_iterations
                ):
                    break
        finally:
            self.stats.stopped_at = time.time()
            log.info(
                "outbox_worker_stopped",
                processed=self.stats.processed,
                empty=self.stats.empty,
                errors=self.stats.errors,
                iterations=self.stats.iterations,
            )
        return self.stats


def run(app, handlers: Mapping[str, Callable], **kwargs) -> WorkerStats:
    """Convenience entry point used by the CLI.

    ``handlers`` is the HANDLERS mapping exposed by ``app/cli/outbox.py``.
    """
    return OutboxWorker(app, handlers=handlers, **kwargs).run()
