"""Audit-chain verification and backfill CLI.

Expose the :func:`verify_chain` and :func:`backfill` helpers so
operators can run them from the shell.

    flask audit verify-chain --tenant 42
    flask audit backfill --tenant 42
"""
from __future__ import annotations

import click
from flask.cli import AppGroup, with_appcontext

from app.services.audit_chain import backfill, verify_chain

audit_cli = AppGroup("audit", help="Audit-chain integrity tools.")


@audit_cli.command("verify-chain")
@click.option("--tenant", required=True, type=click.IntRange(min=1))
@with_appcontext
def verify_chain_cmd(tenant: int) -> None:
    """Recompute every chained-hash row and report breaks."""
    report = verify_chain(tenant)
    click.echo(
        f"tenant={report.tenant_id} checked={report.checked} "
        f"unhashed={report.unhashed} breaks={len(report.breaks)}"
    )
    for brk in report.breaks:
        click.echo(
            f"  break id={brk.at_id} reason={brk.reason} "
            f"expected={brk.expected[:12]}... found={brk.found[:12]}..."
        )
    if report.breaks or report.unhashed:
        raise click.ClickException("audit chain is not clean")


@audit_cli.command("backfill")
@click.option("--tenant", required=True, type=click.IntRange(min=1))
@with_appcontext
def backfill_cmd(tenant: int) -> None:
    """Fill ``prev_event_hash`` and ``event_hash`` for pre-chain rows."""
    hashed = backfill(tenant)
    click.echo(f"tenant={tenant} backfilled={hashed}")
