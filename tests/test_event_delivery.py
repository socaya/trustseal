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
        "document.draft.deleted",
        "document.draft.updated",
        "document.file.ingested",
        "document.snapshot.created",
        "envelope.cancelled",
        "envelope.draft.created",
        "envelope.prepared",
        "envelope.review.acknowledged",
        "envelope.review.declined",
        "evidence.checkpoint.issued",
        "evidence.crl.captured",
        "evidence.dossier.issued",
        "evidence.dss.issued",
        "evidence.hold.placed",
        "evidence.hold.released",
        "evidence.ocsp.captured",
        "evidence.retention.registered",
        "evidence.timestamp.issued",
        "platform.pdf.sealed",
        "review.receipt.issued",
        "signer.document.endorsed",
        "signer.key.registered",
        "signer.key.revoked",
        "stamp.attestation.issued",
        "stamp.design.approved",
        "stamp.design.proposed",
        "stamp.design.rejected",
        "stamp.pdf.issued",
        "stamp.registration.approved",
        "stamp.registration.requested",
        "stamp.registration.revoked",
        "stamp.use.approved",
        "stamp.use.rejected",
        "stamp.use.requested",
    ]


def test_finish_refuses_expired_or_stale_claim():
    from datetime import datetime, timedelta
    from app.services.event_delivery import finish
    stale = datetime.utcnow() - timedelta(seconds=1)
    with patch("app.services.event_delivery.db") as db:
        query = db.session.query.return_value
        query.filter_by.return_value.with_for_update.return_value.first.return_value = None
        assert finish(12, stale, success=True) is False
        db.session.rollback.assert_called_once()
        db.session.commit.assert_not_called()


def test_outbox_missing_handler_is_not_executed():
    from app.services.event_delivery import deliver_one
    with patch("app.services.event_delivery.claim_next", return_value=(14, "lease")):
        with patch("app.services.event_delivery.db") as db:
            item = db.session.get.return_value
            item.event_type = "arbitrary.module.call"
            with patch("app.services.event_delivery.finish", return_value=True) as finish:
                assert deliver_one({}) is True
                finish.assert_called_once_with(
                    14, "lease", success=False, error="No registered handler"
                )


def test_lease_fencing_rejects_prior_worker_token():
    """A reclaimed event must not be finished by a previous lease holder."""
    from app.services.event_delivery import finish
    with patch("app.services.event_delivery.db") as db:
        db.session.query.return_value.filter_by.return_value.with_for_update.return_value.first.return_value = None
        assert finish(7, "older-lease-uuid", success=True) is False
        db.session.commit.assert_not_called()
        db.session.rollback.assert_called_once()
