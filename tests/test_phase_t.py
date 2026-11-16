"""Phase T — SecurityEvent CSV export + webhook event wildcards."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token


# ============================================================ T1 CSV export


@pytest.fixture
def audit_seed(pg_app):
    from app.extensions import db
    from app.models.event_delivery import SecurityEvent
    from app.models.organization import Organization
    from app.models.system import Role, UserRole
    from app.models.user import User

    org = Organization(name="T Tenant", type="company")
    other_org = Organization(name="Other T Tenant", type="company")
    db.session.add_all([org, other_org])
    db.session.flush()
    role = Role.query.filter_by(name="admin").one_or_none() or Role(
        name="admin", description="test"
    )
    db.session.add(role)
    db.session.flush()
    admin = User(
        username="t-admin",
        email="t-admin@example.test",
        is_active=True,
        organization_id=org.id,
    )
    admin.set_password("phase-t-password-123")
    db.session.add(admin)
    db.session.flush()
    db.session.add(UserRole(user_id=admin.id, role_id=role.id))
    regular = User(
        username="t-regular",
        email="t-regular@example.test",
        is_active=True,
        organization_id=org.id,
    )
    regular.set_password("phase-t-password-123")
    db.session.add(regular)
    db.session.flush()
    base = datetime.utcnow() - timedelta(days=1)
    rows = []
    for idx, action in enumerate([
        "envelope.prepared",
        "envelope.withdrawn",
        "user.login",
        "envelope.sealed",
    ]):
        rows.append(
            SecurityEvent(
                organization_id=org.id,
                actor_id=admin.id,
                action=action,
                resource_type="envelope",
                resource_id=100 + idx,
                outcome="ok",
                correlation_id=f"corr-{idx}",
                created_at=base + timedelta(hours=idx),
            )
        )
    # Noise from another tenant to prove scoping.
    rows.append(
        SecurityEvent(
            organization_id=other_org.id,
            actor_id=None,
            action="envelope.prepared",
            resource_type="envelope",
            resource_id=999,
            outcome="ok",
            correlation_id="cross-tenant",
            created_at=base,
        )
    )
    db.session.add_all(rows)
    db.session.commit()
    return {"org": org, "admin": admin, "regular": regular, "rows": rows}


class TestSecurityEventCSV:
    def test_admin_streams_tenant_rows(self, pg_app, audit_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(audit_seed["admin"].id))
        r = client.get(
            "/api/_internal/security-events/export.csv",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.headers["Content-Type"].startswith("text/csv")
        assert "attachment" in r.headers["Content-Disposition"]
        reader = csv.DictReader(io.StringIO(r.get_data(as_text=True)))
        collected = list(reader)
        # Only the 4 rows from the caller's tenant.
        assert len(collected) == 4
        actions = {row["action"] for row in collected}
        assert actions == {
            "envelope.prepared",
            "envelope.withdrawn",
            "user.login",
            "envelope.sealed",
        }
        # Cross-tenant row must be absent.
        correlation_ids = {row["correlation_id"] for row in collected}
        assert "cross-tenant" not in correlation_ids

    def test_action_prefix_filter(self, pg_app, audit_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(audit_seed["admin"].id))
        r = client.get(
            "/api/_internal/security-events/export.csv?action_prefix=envelope.",
            headers={"Authorization": f"Bearer {token}"},
        )
        rows = list(csv.DictReader(io.StringIO(r.get_data(as_text=True))))
        assert {row["action"] for row in rows} == {
            "envelope.prepared",
            "envelope.withdrawn",
            "envelope.sealed",
        }

    def test_since_until_bounds(self, pg_app, audit_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(audit_seed["admin"].id))
        base = audit_seed["rows"][0].created_at
        # Window that includes only the first row.
        since = base.isoformat()
        until = (base + timedelta(minutes=30)).isoformat()
        r = client.get(
            f"/api/_internal/security-events/export.csv?since={since}&until={until}",
            headers={"Authorization": f"Bearer {token}"},
        )
        rows = list(csv.DictReader(io.StringIO(r.get_data(as_text=True))))
        assert len(rows) == 1
        assert rows[0]["action"] == "envelope.prepared"

    def test_non_admin_forbidden(self, pg_app, audit_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(audit_seed["regular"].id))
        r = client.get(
            "/api/_internal/security-events/export.csv",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    def test_invalid_iso_rejected(self, pg_app, audit_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(audit_seed["admin"].id))
        r = client.get(
            "/api/_internal/security-events/export.csv?since=not-a-date",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400

    def test_max_rows_ceiling_enforced(self, pg_app, audit_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(audit_seed["admin"].id))
        r = client.get(
            "/api/_internal/security-events/export.csv?max_rows=999999",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400


# ============================================================ T2 wildcards


class TestWebhookEventWildcards:
    def test_exact_match_still_works(self, pg_app):
        from app.extensions import db
        from app.models.organization import Organization
        from app.models.user import User
        from app.services import webhooks

        org = Organization(name="Hooks Tenant A", type="company")
        db.session.add(org)
        db.session.flush()
        owner = User(
            username="hook-owner-a",
            email="hook-a@example.test",
            is_active=True,
            organization_id=org.id,
        )
        owner.set_password("phase-t-password-123")
        db.session.add(owner)
        db.session.flush()
        endpoint, _ = webhooks.register_endpoint(
            tenant_id=org.id,
            created_by_id=owner.id,
            url="https://example.test/hook-a",
            events=["envelope.prepared"],
        )
        db.session.commit()
        deliveries = webhooks.fan_out_event(
            tenant_id=org.id,
            event_id="evt-exact",
            event_type="envelope.prepared",
            payload={"envelope_id": 1},
        )
        db.session.commit()
        assert len(deliveries) == 1
        assert deliveries[0].endpoint_id == endpoint.id

    def test_prefix_wildcard_matches(self, pg_app):
        from app.extensions import db
        from app.models.organization import Organization
        from app.models.user import User
        from app.services import webhooks

        org = Organization(name="Hooks Tenant B", type="company")
        db.session.add(org)
        db.session.flush()
        owner = User(
            username="hook-owner-b",
            email="hook-b@example.test",
            is_active=True,
            organization_id=org.id,
        )
        owner.set_password("phase-t-password-123")
        db.session.add(owner)
        db.session.flush()
        webhooks.register_endpoint(
            tenant_id=org.id,
            created_by_id=owner.id,
            url="https://example.test/hook-b",
            events=["envelope.*"],
        )
        db.session.commit()
        # Should match every envelope event.
        for et in ("envelope.prepared", "envelope.withdrawn", "envelope.sealed"):
            deliveries = webhooks.fan_out_event(
                tenant_id=org.id,
                event_id=f"evt-{et}",
                event_type=et,
                payload={"envelope_id": 1},
            )
            db.session.commit()
            assert len(deliveries) == 1
        # Should NOT match a non-envelope event.
        deliveries = webhooks.fan_out_event(
            tenant_id=org.id,
            event_id="evt-user-login",
            event_type="user.login",
            payload={"user_id": 1},
        )
        db.session.commit()
        assert deliveries == []

    def test_catchall_wildcard(self, pg_app):
        from app.extensions import db
        from app.models.organization import Organization
        from app.models.user import User
        from app.services import webhooks

        org = Organization(name="Hooks Tenant C", type="company")
        db.session.add(org)
        db.session.flush()
        owner = User(
            username="hook-owner-c",
            email="hook-c@example.test",
            is_active=True,
            organization_id=org.id,
        )
        owner.set_password("phase-t-password-123")
        db.session.add(owner)
        db.session.flush()
        webhooks.register_endpoint(
            tenant_id=org.id,
            created_by_id=owner.id,
            url="https://example.test/hook-c",
            events=["*"],
        )
        db.session.commit()
        for et in ("envelope.prepared", "user.login", "payment.captured"):
            deliveries = webhooks.fan_out_event(
                tenant_id=org.id,
                event_id=f"evt-c-{et}",
                event_type=et,
                payload={},
            )
            db.session.commit()
            assert len(deliveries) == 1

    def test_invalid_pattern_rejected(self, pg_app):
        from app.extensions import db
        from app.models.organization import Organization
        from app.models.user import User
        from app.services import webhooks

        org = Organization(name="Hooks Tenant D", type="company")
        db.session.add(org)
        db.session.flush()
        owner = User(
            username="hook-owner-d",
            email="hook-d@example.test",
            is_active=True,
            organization_id=org.id,
        )
        owner.set_password("phase-t-password-123")
        db.session.add(owner)
        db.session.flush()
        for bad in ("*.envelope", "envelope.*.sealed", "foo*bar", "has space"):
            with pytest.raises(webhooks.WebhookError):
                webhooks.register_endpoint(
                    tenant_id=org.id,
                    created_by_id=owner.id,
                    url=f"https://example.test/hook-d-{bad}",
                    events=[bad],
                )
