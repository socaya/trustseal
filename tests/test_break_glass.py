"""Break-glass access (K3)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token, decode_token


@pytest.fixture
def seeded(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.system import Role, UserRole
    from app.models.user import User

    org = Organization(name="BreakGlass Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    role = Role.query.filter_by(name="admin").one_or_none() or Role(
        name="admin", description="test"
    )
    db.session.add(role)
    db.session.flush()

    def mk_user(name, email, *, admin=False):
        u = User(
            username=name,
            email=email,
            is_active=True,
            organization_id=org.id,
        )
        u.set_password("breakglasspassword123")
        db.session.add(u)
        db.session.flush()
        if admin:
            db.session.add(UserRole(user_id=u.id, role_id=role.id))
        return u

    admin_a = mk_user("bg-admin-a", "bg-admin-a@example.test", admin=True)
    operator = mk_user("bg-operator", "bg-operator@example.test")
    db.session.commit()
    return {"org": org, "admin": admin_a, "operator": operator}


class TestService:
    def test_self_grant_refused(self, pg_app, seeded):
        from app.services import break_glass

        with pytest.raises(break_glass.BreakGlassError) as exc:
            break_glass.grant(
                operator_id=seeded["admin"].id,
                granted_by_id=seeded["admin"].id,
                scope="emergency.access",
                reason="I need in",
            )
        assert "self_grant_forbidden" in str(exc.value)

    def test_grant_issues_short_lived_token(self, pg_app, seeded):
        from app.extensions import db
        from app.services import break_glass

        issue = break_glass.grant(
            operator_id=seeded["operator"].id,
            granted_by_id=seeded["admin"].id,
            scope="incident.response",
            reason="production outage",
            ttl_minutes=15,
        )
        db.session.commit()
        claims = decode_token(issue.access_token)
        assert claims["sub"] == str(seeded["operator"].id)
        assert claims["break_glass_scope"] == "incident.response"
        assert claims["break_glass_grant_id"] == issue.grant_id
        # Token carries mfa_verified_at so step-up gates pass.
        assert isinstance(claims["mfa_verified_at"], int)

    def test_check_returns_active_grant(self, pg_app, seeded):
        from app.services import break_glass

        issue = break_glass.grant(
            operator_id=seeded["operator"].id,
            granted_by_id=seeded["admin"].id,
            scope="data.export",
            reason="emergency export",
        )
        row = break_glass.check(seeded["operator"].id, "data.export")
        assert row.id == issue.grant_id

    def test_check_rejects_expired(self, pg_app, seeded):
        from app.extensions import db
        from app.models.break_glass_grant import BreakGlassGrant
        from app.services import break_glass

        issue = break_glass.grant(
            operator_id=seeded["operator"].id,
            granted_by_id=seeded["admin"].id,
            scope="data.export",
            reason="emergency",
            ttl_minutes=1,
        )
        db.session.commit()
        row = db.session.get(BreakGlassGrant, issue.grant_id)
        row.expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()
        with pytest.raises(break_glass.BreakGlassError):
            break_glass.check(seeded["operator"].id, "data.export")

    def test_revoked_grant_refused(self, pg_app, seeded):
        from app.extensions import db
        from app.services import break_glass

        issue = break_glass.grant(
            operator_id=seeded["operator"].id,
            granted_by_id=seeded["admin"].id,
            scope="data.export",
            reason="x",
        )
        db.session.commit()
        break_glass.revoke(issue.grant_id, revoked_by_id=seeded["admin"].id)
        db.session.commit()
        with pytest.raises(break_glass.BreakGlassError):
            break_glass.check(seeded["operator"].id, "data.export")

    def test_exercise_increments_count(self, pg_app, seeded):
        from app.extensions import db
        from app.services import break_glass

        issue = break_glass.grant(
            operator_id=seeded["operator"].id,
            granted_by_id=seeded["admin"].id,
            scope="data.export",
            reason="x",
        )
        row = break_glass.check(seeded["operator"].id, "data.export")
        break_glass.exercise(row, actor_id=seeded["operator"].id)
        db.session.commit()
        assert row.use_count == 1
        assert row.last_used_at is not None


class TestApi:
    def test_admin_issues_grant(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["admin"].id))
        r = client.post(
            "/api/_internal/break-glass",
            json={
                "operator_id": seeded["operator"].id,
                "scope": "incident.response",
                "reason": "production outage",
                "ttl_minutes": 15,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        body = r.get_json()
        assert body["grant_id"]
        assert body["access_token"]

    def test_non_admin_forbidden(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["operator"].id))
        r = client.post(
            "/api/_internal/break-glass",
            json={
                "operator_id": seeded["operator"].id,
                "scope": "data.export",
                "reason": "x",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    def test_self_grant_refused_at_api(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["admin"].id))
        r = client.post(
            "/api/_internal/break-glass",
            json={
                "operator_id": seeded["admin"].id,
                "scope": "data.export",
                "reason": "I need to debug",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400
        body = r.get_data(as_text=True)
        # The problem-detail normaliser slugifies underscores to
        # dashes in the ``type`` URL; either form is fine.
        assert (
            "self_grant_forbidden" in body
            or "self-grant-forbidden" in body
        )
