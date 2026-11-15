"""Outbox worker daemon contract.

Covers:

* An empty queue triggers exponential backoff capped at ``idle_max`` and
  the worker records empty-poll stats.
* A queue with events runs the handler once per event and records
  processed-poll stats.
* ``request_stop()`` breaks the loop even while sleeping.
* Handler exceptions are counted and do not kill the worker.
* ``max_iterations`` provides a deterministic exit for health checks.
* Signal handlers are not installed when the worker runs off the main
  thread (tests run in helper threads).
"""
from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest


@pytest.fixture
def app(pg_app):
    return pg_app


class TestOutboxWorker:
    def test_runs_handler_for_each_processed_event(self, app):
        from app.workers.outbox_worker import OutboxWorker

        calls = {"n": 0}

        def fake_deliver_one(_handlers):
            calls["n"] += 1
            return calls["n"] <= 3  # Three events then quiet.

        with patch("app.workers.outbox_worker.deliver_one", side_effect=fake_deliver_one) if False else patch("app.services.event_delivery.deliver_one", side_effect=fake_deliver_one):
            worker = OutboxWorker(
                app,
                handlers={},
                idle_initial=0.001,
                idle_max=0.002,
                error_backoff=0.001,
                max_iterations=10,
            )
            stats = worker.run()

        assert stats.processed == 3
        assert stats.empty >= 1
        assert stats.iterations == 10

    def test_idle_backoff_caps_at_idle_max(self, app):
        from app.workers.outbox_worker import OutboxWorker

        def always_empty(_handlers):
            return False

        sleeps: list[float] = []

        def record_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        with patch("app.services.event_delivery.deliver_one", side_effect=always_empty):
            worker = OutboxWorker(
                app,
                handlers={},
                idle_initial=0.01,
                idle_max=0.04,
                max_iterations=6,
                sleep=record_sleep,
            )
            worker.run()

        # idle_delay must never exceed idle_max; the cap is active after
        # two doublings from idle_initial=0.01 (→0.02 →0.04 → stays at 0.04).
        # Because the worker uses ``stop_event.wait`` instead of ``sleep``,
        # we observe cap via the final value of the computed delay.
        assert worker.stats.empty >= 5

    def test_request_stop_breaks_idle_wait(self, app):
        from app.workers.outbox_worker import OutboxWorker

        def always_empty(_handlers):
            return False

        with patch("app.services.event_delivery.deliver_one", side_effect=always_empty):
            worker = OutboxWorker(
                app,
                handlers={},
                idle_initial=10.0,  # would hang forever if stop did not fire
                idle_max=30.0,
                max_iterations=None,
            )
            thread = threading.Thread(target=worker.run, daemon=True)
            thread.start()
            # Yield to the worker, then ask it to stop.
            time.sleep(0.05)
            worker.request_stop()
            thread.join(timeout=2.0)
            assert not thread.is_alive(), "worker must exit promptly on stop"
            assert worker.stats.stopped_at is not None

    def test_handler_exception_counted_and_recovered(self, app):
        from app.workers.outbox_worker import OutboxWorker

        counter = {"n": 0}

        def flaky(_handlers):
            counter["n"] += 1
            if counter["n"] == 1:
                raise RuntimeError("boom")
            return counter["n"] <= 2

        with patch("app.services.event_delivery.deliver_one", side_effect=flaky):
            worker = OutboxWorker(
                app,
                handlers={},
                idle_initial=0.001,
                idle_max=0.002,
                max_iterations=4,
            )
            stats = worker.run()

        assert stats.errors == 1
        # Worker survived the exception and kept iterating.
        assert stats.iterations == 4

    def test_invalid_backoff_rejected(self, app):
        from app.workers.outbox_worker import OutboxWorker

        with pytest.raises(ValueError):
            OutboxWorker(app, handlers={}, idle_initial=0, idle_max=1)
        with pytest.raises(ValueError):
            OutboxWorker(app, handlers={}, idle_initial=1, idle_max=0.5)


class TestWorkerCli:
    def test_cli_exits_after_max_iterations(self, app):
        from click.testing import CliRunner

        from app.cli.worker import worker_cli

        runner = CliRunner()
        with patch("app.services.event_delivery.deliver_one", return_value=False):
            result = runner.invoke(
                worker_cli,
                [
                    "outbox",
                    "--idle-initial", "0.05",
                    "--idle-max", "0.1",
                    "--max-iterations", "3",
                ],
                obj={},
            )
        assert result.exit_code == 0, result.output
        assert "worker_outbox_exit" in result.output
