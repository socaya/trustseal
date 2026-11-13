"""Operator-only outbox inspection and bounded dispatch commands.

Invocation: flask outbox status; flask outbox drain --limit 50
Only built-in, allowlisted internal event consumers are registered here.
Never call untrusted code based on an event's payload.
"""
import click
from flask.cli import AppGroup, with_appcontext
from app.extensions import db
from app.models.event_delivery import OutboxEvent
from app.models.documents.document import Document
from app.models.documents.document_snapshot import DocumentSnapshot
from app.models.documents.document_blob import DocumentBlob
from app.services.event_delivery import deliver_one

outbox_cli = AppGroup("outbox")


def _verify_document_event(payload, key):
    document_id = payload.get("aggregate_id")
    if type(document_id) is not int:
        raise ValueError("Invalid aggregate ID")
    doc = db.session.get(Document, document_id)
    if doc is None:
        raise ValueError("Document no longer exists")
    if key.startswith("document-snapshot:"):
        revision = int(key.rsplit(":", 1)[-1])
        if DocumentSnapshot.query.filter_by(document_id=doc.id, revision=revision).first() is None:
            raise ValueError("Missing snapshot manifest")
    elif key.startswith("document-file:"):
        revision = int(key.rsplit(":", 1)[-1])
        if DocumentBlob.query.filter_by(document_id=doc.id, revision=revision).first() is None:
            raise ValueError("Missing file manifest")
    # Internal consistency acknowledgement only; not an external notification.


HANDLERS = {
    "document.draft.created": _verify_document_event,
    "document.draft.updated": _verify_document_event,
    "document.draft.deleted": _verify_document_event,
    "document.snapshot.created": _verify_document_event,
    "document.file.ingested": _verify_document_event,
}


@outbox_cli.command("status")
@with_appcontext
def status():
    """Print queue status, without exposing event payloads."""
    from sqlalchemy import func
    rows = db.session.query(OutboxEvent.state, func.count(OutboxEvent.id)).group_by(
        OutboxEvent.state
    ).all()
    for state, count in rows:
        click.echo("%s: %s" % (state, count))


@outbox_cli.command("drain")
@click.option("--limit", default=25, type=click.IntRange(1, 1000))
@with_appcontext
def drain(limit):
    """Consume a bounded number of due events; run repeatedly via supervisor."""
    processed = 0
    for _ in range(limit):
        if not deliver_one(HANDLERS):
            break
        processed += 1
    click.echo("Processed %s event attempt(s)" % processed)


@outbox_cli.command("retry-dead")
@click.argument("event_id", type=int)
@click.option("--confirm", is_flag=True, required=True, help="Explicitly approve one dead-letter retry")
@with_appcontext
def retry_dead(event_id, confirm):
    """Manually retry a single dead event after investigating its failure."""
    from datetime import datetime
    item = db.session.query(OutboxEvent).filter_by(
        id=event_id, state="dead"
    ).with_for_update().first()
    if item is None:
        raise click.ClickException("Dead-letter item not found")
    if item.event_type not in HANDLERS:
        raise click.ClickException("Handler not registered; retry refused")
    item.state = "pending"
    item.attempts = 0
    item.next_attempt_at = datetime.utcnow()
    item.locked_until = None
    item.lease_token = None
    item.last_error = None
    db.session.commit()
    click.echo("Retry queued for event %s" % event_id)
