"""SCIM service account lifecycle (L1)."""
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

    org = Organization(name="SCIM Lifecycle Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    role = Role.query.filter_by(name="admin").one_or_none() or Role(
        name="admin", description="test"
    )
    db.session.add(role)
    db.session.flush()
    admin = User(
        username="scim-admin",
        email="scim-admin@example.test",
        is_active=True,
        organization_id=org.id,
    )
    admin.set_password("scimpassword12345")
    db.session.add(admin)
    db.session.flush()
    db.session.add(UserRole(user_id=admin.id, role_id=role.id))
    regular = User(
        username="scim-regular",
        email="scim-regular@example.test",
        is_active=True,
        organization_id=org.id,
    )
    regular.set_password("scimpassword12345")
    db.session.add(regular)
    db.session.commit()
    return {"org": org, "admin": admin, "regular": regular}


class TestService:
    def test_mint_with_expiry(self, pg_app, seeded):
        from app.services import scim

        row, token = scim.mint_token(
            tenant_id=seeded["org"].id,
            created_by_id=seeded["admin"].id,
            display_name="Okta",
            expires_in_days=30,
        )
        assert token.startswith("scim_")
        assert row.expires_at is not None

    def test_rotate_revokes_old_and_issues_new(self, pg_app, seeded):
        from app.extensions import db
        from app.services import scim

        old, _ = scim.mint_token(
            tenant_id=seeded["org"].id,
            created_by_id=seeded["admin"].id,
            display_name="Okta",
        )
        db.session.commit()
        new, token = scim.rotate_token(
            old.id,
            tenant_id=seeded["org"].id,
            rotated_by_id=seeded["admin"].id,
        )
        db.session.commit()
        assert new.id != old.id
        assert new.rotated_from_id == old.id
        db.session.refresh(old)
        assert old.active is False
        assert old.revoked_at is not None
        assert old.revoke_reason == "rotated"

    def test_expired_token_denied(self, pg_app, seeded):
        from app.extensions import db
        from app.models.scim import ScimServiceAccount
        from app.services import scim as scim_service

        row, token = scim_service.mint_token(
            tenant_id=seeded["org"].id,
            created_by_id=seeded["admin"].id,
            display_name="Okta",
        )
        db.session.commit()
        # Force expiry in the past.
        row.expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()
        client = pg_app.test_client()
        r = client.get(
            "/scim/v2/Users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 401

    def test_revoked_token_denied(self, pg_app, seeded):
        from app.extensions import db
        from app.services import scim as scim_service

        row, token = scim_service.mint_token(
            tenant_id=seeded["org"].id,
            created_by_id=seeded["admin"].id,
            display_name="Okta",
        )
        db.session.commit()
        scim_service.revoke_token(
            row.id,
            tenant_id=seeded["org"].id,
            revoked_by_id=seeded["admin"].id,
            reason="compromised",
        )
        db.session.commit()
        client = pg_app.test_client()
        r = client.get(
            "/scim/v2/Users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 401


class TestApi:
    def test_admin_creates_and_lists(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["admin"].id))
        r = client.post(
            "/api/scim/service-accounts",
            json={"display_name": "Okta", "expires_in_days": 60},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201, r.get_data(as_text=True)
        assert r.get_json()["token"].startswith("scim_")
        r = client.get(
            "/api/scim/service-accounts",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        accounts = r.get_json()["accounts"]
        assert len(accounts) == 1

    def test_non_admin_forbidden(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["regular"].id))
        r = client.get(
            "/api/scim/service-accounts",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    def test_rotate_returns_new_token(self, pg_app, seeded):
        from app.extensions import db
        from app.services import scim

        row, _ = scim.mint_token(
            tenant_id=seeded["org"].id,
            created_by_id=seeded["admin"].id,
            display_name="Okta",
        )
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["admin"].id))
        r = client.post(
            f"/api/scim/service-accounts/{row.id}/rotate",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201, r.get_data(as_text=True)
        body = r.get_json()
        assert body["token"].startswith("scim_")
        assert body["rotated_from_id"] == row.id

    def test_revoke_endpoint(self, pg_app, seeded):
        from app.extensions import db
        from app.services import scim

        row, _ = scim.mint_token(
            tenant_id=seeded["org"].id,
            created_by_id=seeded["admin"].id,
            display_name="Okta",
        )
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["admin"].id))
        r = client.delete(
            f"/api/scim/service-accounts/{row.id}",
            json={"reason": "operator"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.get_json()["active"] is False
