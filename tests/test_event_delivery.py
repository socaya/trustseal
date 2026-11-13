"""Unit checks for transaction ownership and allowlisted outbox handlers."""
from unittest.mock import MagicMock, patch

import pytest

from app.services.event_delivery import enqueue
from app.cli.outbox import HANDLERS


def test_enqueue_does_not_commit():
    with patch("app.services.event_delivery.db") as db:
        msg = enqueue(
            event_type="document.draft.created",
            aggregate_type="document", aggregate_id=12,
            organization_id=5, actor_id=3,
            action="document.draft.created",
            idempotency_key="document-created:12",
        )
        assert msg.idempotency_key == "document-created:12"
        db.session.add_all.assert_called_once()
        db.session.commit.assert_not_called()


@pytest.mark.parametrize("bad_key", ["", "x" * 129])
def test_enqueue_requires_bounded_idempotency_key(bad_key):
    with pytest.raises(ValueError):
        enqueue(
            event_type="example", aggregate_type="document",
            aggregate_id=12, organization_id=None, actor_id=1,
            action="example", idempotency_key=bad_key,
        )


def test_no_arbitrary_outbox_handlers_are_registered():
    assert sorted(HANDLERS) == [
        "document.draft.created",
        "document.file.ingested",
        "document.snapshot.created",
    ]
