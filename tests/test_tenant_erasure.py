"""Tenant data erasure (K2)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token


@pytest.fixture
def seeded(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.system import Role, UserRole
    from app.models.user import User

    org_a = Organization(name="Erase A", type="company")
    org_b = Organization(name="Erase B", type="company")
    db.session.add_all([org_a, org_b])
    db.session.flush()
    role = Role.query.filter_by(name="admin").one_or_none() or Role(
        name="admin", description="test"
    )
    db.session.add(role)
    db.session.flush()

    def mk_user(name, email, org, *, admin=False):
        u = User(
            username=name,
            email=email,
            first_name="First",
            last_name="Last",
            phone="+15550000",
            is_active=True,
            organization_id=org.id,
        )
        u.set_password("erasepassword12345")
        db.session.add(u)
        db.session.flush()
        if admin:
            db.session.add(UserRole(user_id=u.id, role_id=role.id))
        return u

    admin = mk_user("erase-admin", "erase-admin@example.test", org_a, admin=True)
    target = mk_user("erase-target", "erase-target@example.test", org_a)
    foreign = mk_user("erase-foreign", "erase-foreign@example.test", org_b)
    db.session.commit()
    return {
        "org_a": org_a,
        "org_b": org_b,
        "admin": admin,
        "target": target,
        "foreign": foreign,
    }


class TestService:
    def test_erase_pseudonymises(self, pg_app, seeded):
        from app.extensions import db
        from app.models.user import User
        from app.services import tenant_erasure

        outcome = tenant_erasure.erase_user(
            user_id=seeded["target"].id,
            requested_by_id=seeded["admin"].id,
        )
        db.session.commit()
        refreshed = db.session.get(User, seeded["target"].id)
        assert refreshed.email.startswith("erased-")
        assert refreshed.email.endswith("@redacted.invalid")
        assert refreshed.username.startswith("erased-")
        assert refreshed.first_name is None
        assert refreshed.last_name is None
        assert refreshed.phone is None
        assert refreshed.is_active is False
        assert outcome.pseudonym

    def test_pseudonym_stable(self, pg_app, seeded):
        """Running erase twice (defensive re-apply) yields the same pseudonym."""
        from app.services import tenant_erasure

        p1 = tenant_erasure._pseudonym(seeded["target"].id)
        p2 = tenant_erasure._pseudonym(seeded["target"].id)
        assert p1 == p2

    def test_refuses_self_erasure(self, pg_app, seeded):
        from app.services import tenant_erasure

        with pytest.raises(tenant_erasure.ErasureError) as exc:
            tenant_erasure.erase_user(
                user_id=seeded["admin"].id,
                requested_by_id=seeded["admin"].id,
            )
        assert "self_erasure_forbidden" in str(exc.value)

    def test_refuses_when_legal_hold_active(self, pg_app, seeded):
        from app.extensions import db
        from app.models.evidence_preservation import (
            EvidenceLegalHold,
            EvidenceRetention,
        )
        from app.services import tenant_erasure

        retention = EvidenceRetention(
            organization_id=seeded["org_a"].id,
            artifact_type="finalized_pdf",
            artifact_id=1,
            artifact_sha256="a" * 64,
            retain_until=datetime.utcnow() + timedelta(days=365),
            created_by_id=seeded["admin"].id,
        )
        db.session.add(retention)
        db.session.flush()
        hold = EvidenceLegalHold(
            retention_id=retention.id,
            organization_id=seeded["org_a"].id,
            requested_by_id=seeded["target"].id,
            reason="pending litigation",
        )
        db.session.add(hold)
        db.session.commit()
        with pytest.raises(tenant_erasure.ErasureError) as exc:
            tenant_erasure.erase_user(
                user_id=seeded["target"].id,
                requested_by_id=seeded["admin"].id,
            )
        assert "legal_hold_active" in str(exc.value)

    def test_security_event_recorded(self, pg_app, seeded):
        from app.extensions import db
        from app.models.event_delivery import SecurityEvent
        from app.services import tenant_erasure

        tenant_erasure.erase_user(
            user_id=seeded["target"].id,
            requested_by_id=seeded["admin"].id,
        )
        db.session.commit()
        count = SecurityEvent.query.filter_by(
            action="user.erased",
            actor_id=seeded["admin"].id,
            resource_id=seeded["target"].id,
        ).count()
        assert count == 1


class TestApi:
    def test_admin_erases_user(self, pg_app, seeded):
        from app.extensions import db
        from app.models.user import User

        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["admin"].id))
        r = client.post(
            f"/api/organizations/{seeded['org_a'].id}/users/{seeded['target'].id}/erase",
            json={"reason": "gdpr_article_17"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        db.session.expire_all()
        refreshed = db.session.get(User, seeded["target"].id)
        assert refreshed.email.endswith("@redacted.invalid")

    def test_foreign_user_404(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["admin"].id))
        r = client.post(
            f"/api/organizations/{seeded['org_a'].id}/users/{seeded['foreign'].id}/erase",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404

    def test_self_erase_refused(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["admin"].id))
        r = client.post(
            f"/api/organizations/{seeded['org_a'].id}/users/{seeded['admin'].id}/erase",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 409
