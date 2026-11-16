"""Operator CLI for envelope lifecycle tasks (N1 + N2 scaffolding)."""
from __future__ import annotations

import click
from flask.cli import AppGroup

from app.extensions import db


envelopes_cli = AppGroup("envelopes", help="Envelope lifecycle operator tools")


@envelopes_cli.command("expire-stale")
def expire_stale_command():
    """Auto-withdraw prepared envelopes past their expires_at."""
    from app.services.envelope_expiry import cancel_expired_envelopes

    outcomes = cancel_expired_envelopes()
    db.session.commit()
    click.echo(f"withdrawn={len(outcomes)}")


def register_cli(app):
    app.cli.add_command(envelopes_cli)
