"""Long-running worker daemons started through the Flask CLI.

Invocation example (systemd / supervisor / launchd):

    flask --app main.py worker outbox

Options are provided for operators who need to tune backoff. The daemon
exits 0 on a graceful SIGTERM / SIGINT. systemd should be configured
with ``Restart=always`` and ``RestartSec=5``.
"""
from __future__ import annotations

import click
from flask import current_app
from flask.cli import AppGroup, with_appcontext

from app.workers.outbox_worker import run as run_outbox

worker_cli = AppGroup("worker", help="Run long-lived background workers.")


@worker_cli.command("outbox")
@click.option("--idle-initial", default=0.25, show_default=True, type=click.FloatRange(min=0.05, max=10.0))
@click.option("--idle-max", default=5.0, show_default=True, type=click.FloatRange(min=0.1, max=60.0))
@click.option(
    "--max-iterations",
    default=None,
    type=click.IntRange(min=1),
    help="Exit after this many loop iterations. Primarily for health checks.",
)
@with_appcontext
def outbox(idle_initial: float, idle_max: float, max_iterations: int | None) -> None:
    """Drain the outbox continuously until SIGTERM/SIGINT."""
    from app.cli.outbox import HANDLERS

    stats = run_outbox(
        current_app._get_current_object(),  # type: ignore[attr-defined]
        HANDLERS,
        idle_initial=idle_initial,
        idle_max=idle_max,
        max_iterations=max_iterations,
    )
    click.echo(
        "worker_outbox_exit "
        f"processed={stats.processed} empty={stats.empty} "
        f"errors={stats.errors} iterations={stats.iterations}"
    )
