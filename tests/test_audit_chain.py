"""Chained-hash integrity for SecurityEvent rows.

Covers:

* Inserting a new event on flush fills ``prev_event_hash`` and
  ``event_hash`` automatically.
* The first event in a tenant chains to the ``GENESIS`` sentinel.
* Verification passes on a clean chain and surfaces breaks when a
  row is tampered with.
* Verification is tenant-scoped: cross-tenant contamination is
  impossible because the hook chains per tenant.
* Backfill assigns hashes to rows written before the migration.
* Deleting a row in the middle is detected as a break at the row
  that used to follow it.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.services import audit_chain


def _mk_tenant(name: str):
    from app.extensions import db
    from app.models.organization import Organization

    org = Organization(name=name)
    db.session.add(org)
    db.session.flush()
    return org


def _mk_event(
    org_id: int, *, action: str = "test.event", actor_id: int | None = None
):
    from app.extensions import db
    from app.models.event_delivery import SecurityEvent

    evt = SecurityEvent(
        organization_id=org_id,
        actor_id=actor_id,
        action=action,
        resource_type="test",
        resource_id=1,
        outcome="success",
        correlation_id=uuid.uuid4().hex,
    )
    db.session.add(evt)
    return evt


@pytest.fixture
def tenants(pg_app):
    from app.extensions import db

    a = _mk_tenant("Chain Tenant A")
    b = _mk_tenant("Chain Tenant B")
    db.session.commit()
    return {"a": a, "b": b}


class TestFlushHook:
    def test_first_event_chains_to_genesis(self, pg_app, tenants):
        from app.extensions import db

        evt = _mk_event(tenants["a"].id)
        db.session.commit()
        assert evt.prev_event_hash == audit_chain.GENESIS
        assert evt.event_hash is not None
        assert len(evt.event_hash) == 64

    def test_second_event_chains_to_first(self, pg_app, tenants):
        from app.extensions import db

        first = _mk_event(tenants["a"].id, action="first")
        db.session.commit()
        second = _mk_event(tenants["a"].id, action="second")
        db.session.commit()
        assert second.prev_event_hash == first.event_hash
        assert second.event_hash != first.event_hash

    def test_tenants_chain_independently(self, pg_app, tenants):
        from app.extensions import db

        a_first = _mk_event(tenants["a"].id, action="a1")
        b_first = _mk_event(tenants["b"].id, action="b1")
        db.session.commit()
        # Both start from GENESIS — their chains never cross.
        assert a_first.prev_event_hash == audit_chain.GENESIS
        assert b_first.prev_event_hash == audit_chain.GENESIS
        a_second = _mk_event(tenants["a"].id, action="a2")
        db.session.commit()
        assert a_second.prev_event_hash == a_first.event_hash

    def test_untenanted_events_chain_under_bucket(self, pg_app):
        from app.extensions import db

        first = _mk_event(org_id=None, action="platform.boot")
        db.session.commit()
        assert first.event_hash is not None


class TestVerification:
    def test_clean_chain_is_ok(self, pg_app, tenants):
        from app.extensions import db

        for i in range(5):
            _mk_event(tenants["a"].id, action=f"evt-{i}")
            db.session.commit()
        report = audit_chain.verify_chain(tenants["a"].id)
        assert report.ok()
        assert report.checked == 5
        assert report.breaks == ()

    def test_tampered_field_breaks_chain(self, pg_app, tenants):
        from app.extensions import db
        from app.models.event_delivery import SecurityEvent

        _mk_event(tenants["a"].id, action="before")
        db.session.commit()
        target = _mk_event(tenants["a"].id, action="tamper-target")
        db.session.commit()
        _mk_event(tenants["a"].id, action="after")
        db.session.commit()
        # Rewrite an attribute without recomputing the hash — simulates
        # a direct DB-level mutation.
        db.session.query(SecurityEvent).filter_by(id=target.id).update(
            {"action": "tampered"}
        )
        db.session.commit()
        report = audit_chain.verify_chain(tenants["a"].id)
        assert not report.ok()
        ids = [b.at_id for b in report.breaks]
        assert target.id in ids

    def test_prev_hash_mismatch_detected(self, pg_app, tenants):
        from app.extensions import db
        from app.models.event_delivery import SecurityEvent

        _mk_event(tenants["a"].id, action="one")
        db.session.commit()
        target = _mk_event(tenants["a"].id, action="two")
        db.session.commit()
        db.session.query(SecurityEvent).filter_by(id=target.id).update(
            {"prev_event_hash": "0" * 64}
        )
        db.session.commit()
        report = audit_chain.verify_chain(tenants["a"].id)
        assert any(
            b.reason == "prev_event_hash does not match predecessor"
            and b.at_id == target.id
            for b in report.breaks
        )

    def test_middle_row_deletion_detected(self, pg_app, tenants):
        from app.extensions import db
        from app.models.event_delivery import SecurityEvent

        a = _mk_event(tenants["a"].id, action="one")
        db.session.commit()
        b = _mk_event(tenants["a"].id, action="two")
        db.session.commit()
        c = _mk_event(tenants["a"].id, action="three")
        db.session.commit()
        db.session.query(SecurityEvent).filter_by(id=b.id).delete()
        db.session.commit()
        report = audit_chain.verify_chain(tenants["a"].id)
        # ``c`` now follows ``a`` but still carries ``b``'s hash as
        # prev → chain break at ``c``.
        assert any(brk.at_id == c.id for brk in report.breaks)

    def test_cross_tenant_breaks_do_not_leak(self, pg_app, tenants):
        from app.extensions import db
        from app.models.event_delivery import SecurityEvent

        # Clean chain in tenant B.
        _mk_event(tenants["b"].id)
        _mk_event(tenants["b"].id)
        db.session.commit()
        # Tamper in tenant A.
        target = _mk_event(tenants["a"].id, action="tamper")
        db.session.commit()
        db.session.query(SecurityEvent).filter_by(id=target.id).update(
            {"outcome": "forged"}
        )
        db.session.commit()
        assert audit_chain.verify_chain(tenants["b"].id).ok()
        assert not audit_chain.verify_chain(tenants["a"].id).ok()


class TestBackfill:
    def test_hashes_pre_chain_rows(self, pg_app, tenants):
        from app.extensions import db
        from app.models.event_delivery import SecurityEvent

        evt = _mk_event(tenants["a"].id, action="legacy")
        db.session.commit()
        # Simulate the pre-migration state by nulling the hashes.
        db.session.query(SecurityEvent).filter_by(id=evt.id).update(
            {"prev_event_hash": None, "event_hash": None}
        )
        db.session.commit()
        assert (
            db.session.get(SecurityEvent, evt.id).event_hash is None
        )
        hashed = audit_chain.backfill(tenants["a"].id)
        assert hashed == 1
        row = db.session.get(SecurityEvent, evt.id)
        assert row.event_hash is not None
        assert audit_chain.verify_chain(tenants["a"].id).ok()

    def test_backfill_idempotent(self, pg_app, tenants):
        from app.extensions import db

        _mk_event(tenants["a"].id)
        db.session.commit()
        assert audit_chain.backfill(tenants["a"].id) == 0


class TestCli:
    def test_verify_chain_cli_exit_zero_on_clean(self, pg_app, tenants):
        from click.testing import CliRunner
        from app.extensions import db

        _mk_event(tenants["a"].id)
        db.session.commit()
        from app.cli.audit import audit_cli

        runner = CliRunner()
        result = runner.invoke(
            audit_cli, ["verify-chain", "--tenant", str(tenants["a"].id)]
        )
        assert result.exit_code == 0, result.output
        assert "breaks=0" in result.output

    def test_verify_chain_cli_exit_nonzero_on_break(self, pg_app, tenants):
        from click.testing import CliRunner
        from app.extensions import db
        from app.models.event_delivery import SecurityEvent

        target = _mk_event(tenants["a"].id, action="tamper")
        db.session.commit()
        db.session.query(SecurityEvent).filter_by(id=target.id).update(
            {"outcome": "forged"}
        )
        db.session.commit()
        from app.cli.audit import audit_cli

        runner = CliRunner()
        result = runner.invoke(
            audit_cli, ["verify-chain", "--tenant", str(tenants["a"].id)]
        )
        assert result.exit_code != 0
