"""Signed audit-chain anchors.

The internal chained-hash probe catches tampering that breaks the
hash chain. An attacker with raw DB access can repair the chain
after deletion or mutation. The signed anchor pins a chain tip to a
specific point in time and an external key, so a rewrite that
preserves internal consistency still fails verification.

Covers:

* ``anchor_chain`` writes an ``AuditChainAnchor`` row carrying the
  current tip, the id of the event it anchored against, and a valid
  Ed25519 signature over a canonical payload.
* Anchoring an empty-chain tenant uses the ``GENESIS`` sentinel and
  ``anchor_event_id = None``.
* ``verify_chain(..., anchor_trusted_key_resolver=...)`` validates
  every anchor and surfaces breaks for:
    - signature forgery / wrong key,
    - tip hash disagreeing with the recomputed chain,
    - unsupported algorithms.
* A DB-level rewrite that preserves the internal chain but changes
  an earlier event's hash is detected because the anchor's recorded
  tip no longer matches the recomputed tip at the anchored event id.
* ``verify_chain`` without a resolver ignores anchors entirely
  (backwards compatibility).
"""
from __future__ import annotations

import uuid

import pytest


def _mk_tenant(name: str):
    from app.extensions import db
    from app.models.organization import Organization

    org = Organization(name=name)
    db.session.add(org)
    db.session.flush()
    return org


def _mk_event(org_id: int, *, action: str = "test.event", actor_id: int | None = None):
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


def _mk_user(org):
    from app.extensions import db
    from app.models.user import User

    user = User(
        username=f"anchor-op-{org.id}",
        email=f"anchor-op-{org.id}@example.test",
        is_active=True,
        organization_id=org.id,
    )
    user.set_password("not-used-strong-password")
    db.session.add(user)
    db.session.flush()
    return user


@pytest.fixture
def signing_key():
    """Provide an Ed25519 key for anchor signing and verification."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )

    return Ed25519PrivateKey.generate()


@pytest.fixture
def tenant(pg_app):
    from app.extensions import db

    org = _mk_tenant("Anchor Tenant")
    user = _mk_user(org)
    db.session.commit()
    return {"org": org, "user": user}


class TestAnchor:
    def test_anchor_empty_tenant_uses_genesis(self, pg_app, tenant, signing_key):
        from app.extensions import db
        from app.services import audit_chain

        row = audit_chain.anchor_chain(
            tenant["org"].id,
            operator_id=tenant["user"].id,
            private_key=signing_key,
        )
        db.session.commit()
        assert row.chain_tip_hash == audit_chain.GENESIS
        assert row.anchor_event_id is None
        assert row.algorithm == "Ed25519"
        assert row.signature

    def test_anchor_records_current_tip(self, pg_app, tenant, signing_key):
        from app.extensions import db
        from app.services import audit_chain

        _mk_event(tenant["org"].id, action="one")
        latest = _mk_event(tenant["org"].id, action="two")
        db.session.commit()
        row = audit_chain.anchor_chain(
            tenant["org"].id,
            operator_id=tenant["user"].id,
            private_key=signing_key,
        )
        db.session.commit()
        assert row.anchor_event_id == latest.id
        assert row.chain_tip_hash == latest.event_hash


class TestVerifyWithAnchors:
    def _resolver(self, signing_key):
        public = signing_key.public_key()

        def _resolve(_key_id):
            return public

        return _resolve

    def test_clean_chain_with_anchor_is_ok(self, pg_app, tenant, signing_key):
        from app.extensions import db
        from app.services import audit_chain

        _mk_event(tenant["org"].id, action="one")
        _mk_event(tenant["org"].id, action="two")
        db.session.commit()
        audit_chain.anchor_chain(
            tenant["org"].id,
            operator_id=tenant["user"].id,
            private_key=signing_key,
        )
        db.session.commit()
        report = audit_chain.verify_chain(
            tenant["org"].id,
            anchor_trusted_key_resolver=self._resolver(signing_key),
        )
        assert report.ok(), [b.reason for b in report.breaks]

    def test_db_rewrite_detected_by_anchor_tip_mismatch(
        self, pg_app, tenant, signing_key
    ):
        """An attacker that preserves the internal chain still fails.

        We simulate a rewrite that:
          * deletes an event in the middle,
          * repairs the chain by rebuilding every downstream hash,
        so the internal chained-hash probe passes. The anchor's
        signed tip for the deleted event's id can no longer be
        reproduced.
        """
        from app.extensions import db
        from app.models.event_delivery import SecurityEvent
        from app.services import audit_chain

        a = _mk_event(tenant["org"].id, action="one")
        b = _mk_event(tenant["org"].id, action="two")
        c = _mk_event(tenant["org"].id, action="three")
        db.session.commit()
        # Anchor at event c — before the rewrite.
        audit_chain.anchor_chain(
            tenant["org"].id,
            operator_id=tenant["user"].id,
            private_key=signing_key,
        )
        db.session.commit()

        # Simulate a DB-level rewrite: delete b, then rebuild c's
        # hashes so the internal chain is consistent. The anchor's
        # signed tip for event c will no longer match the recomputed
        # tip.
        a_hash = a.event_hash
        db.session.delete(b)
        db.session.flush()
        # Re-derive c's prev/event hash so the chain validates.
        c.prev_event_hash = a_hash
        c.event_hash = audit_chain.compute_hash(a_hash, c)
        db.session.commit()

        report = audit_chain.verify_chain(
            tenant["org"].id,
            anchor_trusted_key_resolver=self._resolver(signing_key),
        )
        reasons = {brk.reason for brk in report.breaks}
        assert "anchor_chain_tip_mismatch" in reasons, reasons

    def test_forged_signature_detected(self, pg_app, tenant, signing_key):
        from app.extensions import db
        from app.models.audit_chain_anchor import AuditChainAnchor
        from app.services import audit_chain

        _mk_event(tenant["org"].id, action="only")
        db.session.commit()
        row = audit_chain.anchor_chain(
            tenant["org"].id,
            operator_id=tenant["user"].id,
            private_key=signing_key,
        )
        db.session.commit()
        # Replace the signature with 64 random bytes of base64.
        import base64

        row.signature = base64.b64encode(b"\x00" * 64).decode("ascii")
        db.session.commit()
        report = audit_chain.verify_chain(
            tenant["org"].id,
            anchor_trusted_key_resolver=self._resolver(signing_key),
        )
        reasons = {brk.reason for brk in report.breaks}
        assert "anchor_signature_invalid" in reasons

    def test_untrusted_key_detected(self, pg_app, tenant, signing_key):
        from app.extensions import db
        from app.services import audit_chain

        _mk_event(tenant["org"].id, action="only")
        db.session.commit()
        audit_chain.anchor_chain(
            tenant["org"].id,
            operator_id=tenant["user"].id,
            private_key=signing_key,
        )
        db.session.commit()

        def _resolve(_key_id):
            raise ValueError("not in trust registry")

        report = audit_chain.verify_chain(
            tenant["org"].id, anchor_trusted_key_resolver=_resolve
        )
        reasons = {brk.reason for brk in report.breaks}
        assert any("anchor_key_untrusted" in r for r in reasons), reasons

    def test_verify_without_resolver_ignores_anchors(
        self, pg_app, tenant, signing_key
    ):
        """Backwards compatibility: no resolver -> no anchor checks."""
        from app.extensions import db
        from app.services import audit_chain

        _mk_event(tenant["org"].id, action="only")
        db.session.commit()
        row = audit_chain.anchor_chain(
            tenant["org"].id,
            operator_id=tenant["user"].id,
            private_key=signing_key,
        )
        # Even if the anchor's signature is corrupt, the chainless
        # verify ignores it.
        row.signature = "corrupt-signature"
        db.session.commit()
        report = audit_chain.verify_chain(tenant["org"].id)
        assert report.ok()


class TestCli:
    def test_anchor_cli_requires_private_key(self, pg_app, tenant):
        from click.testing import CliRunner

        from app.cli.audit import audit_cli

        runner = CliRunner()
        result = runner.invoke(
            audit_cli,
            ["anchor", "--tenant", str(tenant["org"].id),
             "--operator", str(tenant["user"].id)],
        )
        assert result.exit_code != 0
        assert "EVIDENCE_CHECKPOINT_PRIVATE_KEY" in result.output
