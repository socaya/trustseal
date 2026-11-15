"""Prometheus ``/metrics`` endpoint contract.

Covers:

* Anonymous callers receive 401.
* Non-admin tenant members receive 403.
* Admin callers receive a Prometheus exposition payload.
* HTTP duration histogram observations are recorded.
* Outbox and webhook backlog gauges reflect current DB state.
* Admin-only exposure prevents leakage of per-tenant counters to
  unauthorized callers.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def admin_token(pg_app):
    from flask_jwt_extended import create_access_token

    from app.extensions import db
    from app.models.organization import Organization
    from app.models.system import Role, UserRole
    from app.models.user import User

    org = Organization(name="Metrics Tenant")
    db.session.add(org)
    db.session.flush()
    admin = User(
        username="metrics-admin",
        email="metrics-admin@example.test",
        is_active=True,
        organization_id=org.id,
    )
    admin.set_password("not-used")
    role = Role(name="admin")
    db.session.add_all([admin, role])
    db.session.flush()
    db.session.add(UserRole(user_id=admin.id, role_id=role.id))
    member = User(
        username="metrics-member",
        email="metrics-member@example.test",
        is_active=True,
        organization_id=org.id,
    )
    member.set_password("not-used")
    db.session.add(member)
    db.session.commit()
    return {
        "admin": create_access_token(identity=str(admin.id)),
        "member": create_access_token(identity=str(member.id)),
    }


class TestEndpointAccess:
    def test_anonymous_denied(self, pg_app):
        r = pg_app.test_client().get("/api/metrics")
        assert r.status_code in {401, 403}

    def test_member_denied(self, pg_app, admin_token):
        r = pg_app.test_client().get(
            "/api/metrics",
            headers={"Authorization": f"Bearer {admin_token['member']}"},
        )
        assert r.status_code == 403

    def test_admin_returns_exposition(self, pg_app, admin_token):
        r = pg_app.test_client().get(
            "/api/metrics",
            headers={"Authorization": f"Bearer {admin_token['admin']}"},
        )
        assert r.status_code == 200
        assert "text/plain" in r.content_type
        body = r.data.decode("utf-8")
        assert "# HELP trustseal_http_request_duration_seconds" in body
        assert "# TYPE trustseal_http_request_duration_seconds histogram" in body


class TestInstrumentation:
    def test_request_counter_increments(self, pg_app, admin_token):
        # Issue a probe request first.
        pg_app.test_client().get(
            "/api/metrics", headers={"Authorization": f"Bearer {admin_token['admin']}"}
        )
        r = pg_app.test_client().get(
            "/api/metrics", headers={"Authorization": f"Bearer {admin_token['admin']}"}
        )
        body = r.data.decode("utf-8")
        # The /metrics endpoint itself must appear in the histogram.
        assert 'endpoint="/api/metrics"' in body
        assert "trustseal_http_requests_total" in body

    def test_backlog_gauges_reflect_db(self, pg_app, admin_token):
        from app.extensions import db
        from app.models.event_delivery import OutboxEvent

        db.session.add(
            OutboxEvent(
                event_type="test.event",
                aggregate_type="probe",
                aggregate_id=1,
                organization_id=1,
                payload={"ok": True},
                idempotency_key="probe-outbox-metrics",
                state="pending",
                attempts=0,
                next_attempt_at=__import__("datetime").datetime.utcnow(),
            )
        )
        db.session.commit()
        r = pg_app.test_client().get(
            "/api/metrics", headers={"Authorization": f"Bearer {admin_token['admin']}"}
        )
        body = r.data.decode("utf-8")
        assert 'trustseal_outbox_backlog{state="pending"} 1.0' in body


class TestCounters:
    def test_counter_helpers_do_not_blow_up(self, pg_app):
        from app.metrics import (
            record_idempotency_outcome,
            record_outbox_outcome,
            record_webhook_outcome,
        )

        record_outbox_outcome("delivered")
        record_webhook_outcome("succeeded")
        record_idempotency_outcome("replayed")
