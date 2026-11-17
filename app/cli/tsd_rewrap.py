"""CLI: rotate TSD master KEK or tenant DEKs.

Usage::

    flask tsd rewrap --master --previous <old-secret-key>
    flask tsd rewrap --tenant <organization-id>

The master-KEK path re-wraps every tenant's DEK under the current
``SECRET_KEY``; document ciphertext is not touched. The tenant-DEK path
generates a new random DEK for one tenant and re-encrypts every
document in that tenant under it.
"""
from __future__ import annotations

import click
from flask.cli import AppGroup

from app.services import tsd_format


tsd_cli = AppGroup("tsd", help="TrustSeal Document key-rotation operator commands")


@tsd_cli.command("rewrap")
@click.option("--master", "do_master", is_flag=True, help="Re-wrap all tenant DEKs under the current SECRET_KEY")
@click.option("--previous", "previous_secret", help="Previous SECRET_KEY (required with --master)")
@click.option("--tenant", "tenant_id", type=int, help="Rotate the DEK for one tenant (org id)")
def rewrap_command(do_master: bool, previous_secret: str | None, tenant_id: int | None):
    """Rotate TSD keys. Pass --master OR --tenant <id>."""
    if do_master == bool(tenant_id):
        raise click.ClickException("choose exactly one of --master or --tenant <id>")

    if do_master:
        if not previous_secret:
            raise click.ClickException("--previous <old-secret> is required with --master")
        count = tsd_format.rewrap_master(previous_secret=previous_secret)
        click.echo(f"master-KEK rotation: {count} tenant key(s) re-wrapped")
        return

    assert tenant_id is not None
    count = tsd_format.rotate_tenant_key(tenant_id)
    click.echo(f"tenant DEK rotation: {count} document(s) re-encrypted for tenant {tenant_id}")


def register_cli(app):
    app.cli.add_command(tsd_cli)
