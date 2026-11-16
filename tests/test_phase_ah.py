"""Phase AH — audit chain inclusion proof + notification metric."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from flask_jwt_extended import create_access_token


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}


# ============================================================ AH1 inclusion proof


@pytest.fixture
def ah1_seed(pg_app):
    """Seed a tenant admin + a run of SecurityEvents + a signed anchor."""
    from app.extensions import db
    from app.models.audit_chain_anchor import AuditChainAnchor
    from app.models.event_delivery import SecurityEvent
    from app.models.organization import Organization
    from app.models.system import Role, UserRole
    from app.models.user import User
    from app.services import audit_chain

    org = Organization(name="AH1 Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    role = Role.query.filter_by(name="admin").one_or_none() or Role(
        name="admin", description="test"
    )
    db.session.add(role)
    db.session.flush()
    admin = User(
        username="ah1-admin",
        email="ah1-admin@example.test",
        is_active=True,
        organization_id=org.id,
    )
    admin.set_password("phase-ah-password-123")
    db.session.add(admin)
    db.session.flush()
    db.session.add(UserRole(user_id=admin.id, role_id=role.id))
    db.session.commit()

    # Seed a run of events in the tenant and let the audit_chain
    # hook chain them. The hook fires on commit.
    events = []
    for n in range(4):
        events.append(
            SecurityEvent(
                organization_id=org.id,
                actor_id=admin.id,
                action=f"phase.ah.event.{n}",
                resource_type="probe",
                resource_id=n,
                outcome="ok",
                correlation_id=uuid.uuid4().hex,
            )
        )
    db.session.add_all(events)
    db.session.commit()
    # After the commit the rows carry chained hashes.
    tip_event = (
        SecurityEvent.query.filter_by(organization_id=org.id)
        .order_by(SecurityEvent.id.desc())
        .first()
    )
    # Build + sign an anchor over the tip.
    key = Ed25519PrivateKey.generate()
    tip_payload = {
        "organization_id": org.id,
        "anchor_event_id": tip_event.id,
        "chain_tip_hash": tip_event.event_hash,
    }
    canonical = json.dumps(
        tip_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    signature = key.sign(canonical).hex()
    key_id = hashlib.sha256(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).hexdigest()[:40]
    anchor = AuditChainAnchor(
        organization_id=org.id,
        anchor_event_id=tip_event.id,
        chain_tip_hash=tip_event.event_hash,
        payload=tip_payload,
        algorithm="ed25519",
        key_id=key_id,
        signature=signature,
        operator_id=admin.id,
    )
    db.session.add(anchor)
    db.session.commit()
    return {
        "org": org,
        "admin": admin,
        "events": events,
        "anchor": anchor,
        "key": key,
    }


class TestAuditChainProof:
    def test_proof_slice_replays_to_anchor_tip(self, pg_app, ah1_seed):
        from app.extensions import db
        from app.models.event_delivery import SecurityEvent
        from app.services import audit_chain

        client = pg_app.test_client()
        first_event_id = (
            SecurityEvent.query.filter_by(organization_id=ah1_seed["org"].id)
            .order_by(SecurityEvent.id.asc())
            .first()
            .id
        )
        r = client.get(
            f"/api/_internal/audit/proof?event_id={first_event_id}",
            headers=_auth(ah1_seed["admin"]),
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        body = r.get_json()
        # Rebuild the chain from the event + slice using the DB rows.
        chain_tip = body["event"]["event_hash"]
        for row in body["slice"]:
            assert row["prev_event_hash"] == chain_tip
            chain_tip = row["event_hash"]
        assert chain_tip == body["anchor"]["chain_tip_hash"]

    def test_unknown_event_404(self, pg_app, ah1_seed):
        client = pg_app.test_client()
        r = client.get(
            "/api/_internal/audit/proof?event_id=99999999",
            headers=_auth(ah1_seed["admin"]),
        )
        assert r.status_code == 404

    def test_requires_event_id(self, pg_app, ah1_seed):
        client = pg_app.test_client()
        r = client.get(
            "/api/_internal/audit/proof",
            headers=_auth(ah1_seed["admin"]),
        )
        assert r.status_code == 400

    def test_requires_admin(self, pg_app, ah1_seed):
        from app.extensions import db
        from app.models.user import User

        regular = User(
            username="ah1-regular",
            email="ah1-regular@example.test",
            is_active=True,
            organization_id=ah1_seed["org"].id,
        )
        regular.set_password("phase-ah-password-123")
        db.session.add(regular)
        db.session.commit()
        client = pg_app.test_client()
        r = client.get(
            f"/api/_internal/audit/proof?event_id={ah1_seed['events'][0].id}",
            headers=_auth(regular),
        )
        assert r.status_code == 403

    def test_no_anchor_yet_returns_409(self, pg_app):
        from app.extensions import db
        from app.models.event_delivery import SecurityEvent
        from app.models.organization import Organization
        from app.models.system import Role, UserRole
        from app.models.user import User

        org = Organization(name="AH1 NoAnchor", type="company")
        db.session.add(org)
        db.session.flush()
        role = Role.query.filter_by(name="admin").one_or_none() or Role(
            name="admin", description="test"
        )
        db.session.add(role)
        db.session.flush()
        admin = User(
            username="ah1-noanchor-admin",
            email="ah1-noanchor-admin@example.test",
            is_active=True,
            organization_id=org.id,
        )
        admin.set_password("phase-ah-password-123")
        db.session.add(admin)
        db.session.flush()
        db.session.add(UserRole(user_id=admin.id, role_id=role.id))
        event = SecurityEvent(
            organization_id=org.id,
            actor_id=admin.id,
            action="phase.ah.unanchored",
            resource_type="probe",
            resource_id=1,
            outcome="ok",
            correlation_id=uuid.uuid4().hex,
        )
        db.session.add(event)
        db.session.commit()
        client = pg_app.test_client()
        r = client.get(
            f"/api/_internal/audit/proof?event_id={event.id}",
            headers=_auth(admin),
        )
        assert r.status_code == 409


# ============================================================ AH2 metric


class TestOperatorNotificationMetric:
    def test_publish_bumps_counter(self, pg_app):
        from app.extensions import db
        from app.metrics import operator_notifications_published_total
        from app.models.organization import Organization
        from app.models.user import User
        from app.services import operator_notifications

        org = Organization(name="AH2 Tenant", type="company")
        db.session.add(org)
        db.session.flush()
        actor = User(
            username="ah2-actor",
            email="ah2-actor@example.test",
            is_active=True,
            organization_id=org.id,
        )
        actor.set_password("phase-ah-password-123")
        db.session.add(actor)
        db.session.commit()

        before = operator_notifications_published_total.labels(
            "phase.ah.metric"
        )._value.get()
        operator_notifications.publish(
            organization_id=org.id,
            recipient_user_id=actor.id,
            kind="phase.ah.metric",
            subject_type="probe",
            subject_id=1,
            summary="counter test",
        )
        db.session.commit()
        after = operator_notifications_published_total.labels(
            "phase.ah.metric"
        )._value.get()
        assert after == before + 1
