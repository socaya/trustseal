"""Audit-chain verification, backfill, and signed-anchor CLI.

Expose the chain helpers so operators can run them from the shell:

    flask audit verify-chain --tenant 42
    flask audit backfill --tenant 42
    flask audit anchor --tenant 42 --operator 7

``anchor`` signs the current chain tip with the configured
``EVIDENCE_CHECKPOINT_PRIVATE_KEY`` so a future ``verify-chain`` run
can prove the chain has not been rewritten even if an attacker
preserved internal consistency.
"""
from __future__ import annotations

import click
from flask import current_app
from flask.cli import AppGroup, with_appcontext

from app.services.audit_chain import anchor_chain, backfill, verify_chain

audit_cli = AppGroup("audit", help="Audit-chain integrity tools.")


@audit_cli.command("verify-chain")
@click.option("--tenant", required=True, type=click.IntRange(min=1))
@click.option(
    "--anchors/--no-anchors",
    default=False,
    show_default=True,
    help="Also verify every AuditChainAnchor signature and tip.",
)
@with_appcontext
def verify_chain_cmd(tenant: int, anchors: bool) -> None:
    """Recompute every chained-hash row and report breaks."""
    from app.services.evidence_preservation import trusted_checkpoint_key

    resolver = None
    if anchors:
        def _resolve(key_id: str):
            return trusted_checkpoint_key(current_app.config, key_id)

        resolver = _resolve
    report = verify_chain(tenant, anchor_trusted_key_resolver=resolver)
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


@audit_cli.command("anchor")
@click.option("--tenant", required=True, type=click.IntRange(min=1))
@click.option(
    "--operator",
    required=True,
    type=click.IntRange(min=1),
    help="User id authoring the anchor; recorded in the signed payload.",
)
@with_appcontext
def anchor_cmd(tenant: int, operator: int) -> None:
    """Sign the current chain tip and persist an AuditChainAnchor row."""
    from app.extensions import db
    from app.services.signing_receipts import load_private_key

    key_path = current_app.config.get("EVIDENCE_CHECKPOINT_PRIVATE_KEY")
    if not key_path:
        raise click.ClickException(
            "EVIDENCE_CHECKPOINT_PRIVATE_KEY is not configured"
        )
    private_key = load_private_key(key_path)
    row = anchor_chain(tenant, operator_id=operator, private_key=private_key)
    db.session.commit()
    click.echo(
        f"tenant={tenant} anchor_id={row.id} "
        f"event_id={row.anchor_event_id} tip={row.chain_tip_hash[:12]}..."
    )
