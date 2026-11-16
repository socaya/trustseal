"""Webhook ping + replay (M1)."""
from __future__ import annotations

import pytest
from flask_jwt_extended import create_access_token


@pytest.fixture
def seeded(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.user import User
    from app.models.webhook import WebhookEndpoint

    org = Organization(name="Webhook M1", type="company")
    db.session.add(org)
    db.session.flush()
    admin = User(
        username="webhook-admin",
        email="webhook-admin@example.test",
        is_active=True,
        organization_id=org.id,
    )
    admin.set_password("webhookpassword12345")
    db.session.add(admin)
    db.session.flush()
    endpoint = WebhookEndpoint(
        organization_id=org.id,
        created_by_id=admin.id,
        url="https://receiver.example.test/hook",
        secret_hash="x" * 64,
        events=["envelope.prepared"],
        active=True,
    )
    db.session.add(endpoint)
    db.session.commit()
    return {"org": org, "admin": admin, "endpoint": endpoint}


class TestPing:
    def test_ping_creates_pending_delivery(self, pg_app, seeded):
        from app.extensions import db
        from app.models.webhook import WebhookDelivery

        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["admin"].id))
        r = client.post(
            f"/api/webhooks/{seeded['endpoint'].id}/ping",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"ping-{seeded['endpoint'].id}-1",
            },
        )
        assert r.status_code == 201, r.get_data(as_text=True)
        body = r.get_json()
        assert body["event_type"] == "trustseal.ping"
        assert body["status"] == "pending"
        db.session.expire_all()
        rows = WebhookDelivery.query.filter_by(
            endpoint_id=seeded["endpoint"].id, event_type="trustseal.ping"
        ).all()
        assert len(rows) == 1

    def test_ping_cross_tenant_404(self, pg_app, seeded):
        from app.extensions import db
        from app.models.organization import Organization
        from app.models.user import User

        other = Organization(name="Webhook Other", type="company")
        db.session.add(other)
        db.session.flush()
        intruder = User(
            username="webhook-intruder",
            email="webhook-intruder@example.test",
            is_active=True,
            organization_id=other.id,
        )
        intruder.set_password("webhookpassword12345")
        db.session.add(intruder)
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(intruder.id))
        r = client.post(
            f"/api/webhooks/{seeded['endpoint'].id}/ping",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": "ping-cross-tenant",
            },
        )
        assert r.status_code == 404


class TestReplay:
    def _make_delivery(self, pg_app, seeded, status="dead"):
        from app.extensions import db
        from datetime import datetime
        from app.models.webhook import WebhookDelivery

        delivery = WebhookDelivery(
            endpoint_id=seeded["endpoint"].id,
            organization_id=seeded["org"].id,
            event_id="original-" + status,
            event_type="envelope.prepared",
            payload={"envelope_id": 42},
            status=status,
            retry_count=5,
            next_retry_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
        db.session.add(delivery)
        db.session.commit()
        return delivery

    def test_replay_creates_fresh_pending_delivery(self, pg_app, seeded):
        from app.extensions import db
        from app.models.webhook import WebhookDelivery

        original = self._make_delivery(pg_app, seeded, "dead")
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["admin"].id))
        r = client.post(
            f"/api/webhooks/deliveries/{original.id}/replay",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"replay-{original.id}",
            },
        )
        assert r.status_code == 201, r.get_data(as_text=True)
        body = r.get_json()
        assert body["status"] == "pending"
        assert body["retry_count"] == 0
        db.session.expire_all()
        replay = (
            WebhookDelivery.query.filter(
                WebhookDelivery.id != original.id,
                WebhookDelivery.endpoint_id == original.endpoint_id,
            )
            .order_by(WebhookDelivery.id.desc())
            .first()
        )
        assert replay is not None
        assert (
            replay.payload.get("trustseal_replay_of_delivery_id")
            == original.id
        )
        # Original delivery row unchanged.
        db.session.refresh(original)
        assert original.status == "dead"

    def test_replay_unknown_delivery_404(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["admin"].id))
        r = client.post(
            "/api/webhooks/deliveries/99999/replay",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": "replay-missing",
            },
        )
        assert r.status_code == 404
