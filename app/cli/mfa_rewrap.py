"""CLI: re-wrap every MFA seed under the current SECRET_KEY.

Usage::

    flask mfa rewrap

Operators run this after rotating ``SECRET_KEY`` with the previous
value listed in ``MFA_PREVIOUS_SECRET_KEYS``. The dual-key reader
allows TOTP verification to keep working during the migration; this
CLI migrates the stored seeds so the previous key can later be
removed.
"""
from __future__ import annotations

import click
from flask import current_app
from flask.cli import AppGroup

from app.extensions import db


mfa_cli = AppGroup("mfa", help="MFA key-rotation operator commands")


@mfa_cli.command("rewrap")
def rewrap_command():
    """Re-encrypt every MFA secret under the active SECRET_KEY."""
    from app.services import mfa

    secret = current_app.config.get("SECRET_KEY")
    if not isinstance(secret, str) or len(secret) < 32:
        raise click.ClickException(
            "SECRET_KEY must be set and at least 32 chars"
        )
    summary = mfa.rewrap_all(current_secret=secret)
    db.session.commit()
    click.echo(
        "rewrapped={rewrapped} already_current={already_current} "
        "failed={failed}".format(**summary)
    )


def register_cli(app):
    app.cli.add_command(mfa_cli)
