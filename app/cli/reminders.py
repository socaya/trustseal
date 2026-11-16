"""Operator CLI for the reminder scanner (N2)."""
from __future__ import annotations

import click
from flask.cli import AppGroup

from app.extensions import db


reminders_cli = AppGroup(
    "reminders", help="Scheduled reminder scanner."
)


@reminders_cli.command("scan")
@click.option(
    "--approaching-hours",
    default=48,
    show_default=True,
    type=click.IntRange(min=1, max=720),
)
@click.option(
    "--cooloff-hours",
    default=24,
    show_default=True,
    type=click.IntRange(min=1, max=168),
)
def scan_command(approaching_hours: int, cooloff_hours: int):
    """Send reminder emails to participants nearing invitation expiry."""
    from app.services.reminder_scanner import scan_reminders

    sent = scan_reminders(
        approaching_hours=approaching_hours,
        cooloff_hours=cooloff_hours,
    )
    db.session.commit()
    click.echo(f"reminders_sent={len(sent)}")


def register_cli(app):
    app.cli.add_command(reminders_cli)
