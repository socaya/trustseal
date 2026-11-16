"""Single logout (L3)."""
from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from flask_jwt_extended import create_access_token


@pytest.fixture
def seeded(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.saml_provider import SamlProvider
    from app.models.user import User
    from app.services.refresh_tokens import issue_login_tokens

    org = Organization(name="SLO Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    user = User(
        username="slo-user",
        email="slo-user@example.test",
        is_active=True,
        organization_id=org.id,
    )
    user.set_password("slopassword12345")
    db.session.add(user)
    db.session.flush()
    issue_login_tokens(user.id)
    saml = SamlProvider(
        organization_id=org.id,
        display_name="Test IdP",
        entity_id="https://idp.example.test/entity",
        sso_url="https://idp.example.test/sso",
        x509_cert_pem="-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----",
        audience="trustseal-sp-slo",
        attribute_mapping={
            "email": "email",
            "single_logout_service_url": "https://idp.example.test/slo",
        },
        is_active=True,
        created_by_id=user.id,
    )
    db.session.add(saml)
    db.session.commit()
    return {"org": org, "user": user, "saml": saml}


class TestService:
    def test_revokes_refresh_families(self, pg_app, seeded):
        from app.extensions import db
        from app.models.refresh_token import RefreshTokenFamily
        from app.services import single_logout

        outcome = single_logout.logout_user(seeded["user"].id)
        db.session.commit()
        assert outcome["revoked_families"] >= 1
        active = RefreshTokenFamily.query.filter_by(
            user_id=seeded["user"].id, revoked_at=None
        ).count()
        assert active == 0

    def test_saml_logout_url_built(self, pg_app, seeded):
        from app.services import single_logout

        outcome = single_logout.logout_user(
            seeded["user"].id, saml_provider=seeded["saml"]
        )
        assert outcome["saml_logout_url"]
        parts = urlparse(outcome["saml_logout_url"])
        assert parts.netloc == "idp.example.test"
        q = parse_qs(parts.query)
        assert "SAMLRequest" in q

    def test_saml_without_slo_returns_none(self, pg_app, seeded):
        from app.extensions import db
        from app.services import single_logout

        seeded["saml"].attribute_mapping = {"email": "email"}
        db.session.commit()
        outcome = single_logout.logout_user(
            seeded["user"].id, saml_provider=seeded["saml"]
        )
        assert outcome["saml_logout_url"] is None

    def test_sessions_marked_revoked(self, pg_app, seeded):
        from app.extensions import db
        from app.models.user_session import UserSession
        from app.services import single_logout

        single_logout.logout_user(seeded["user"].id)
        db.session.commit()
        active = UserSession.query.filter_by(
            user_id=seeded["user"].id, revoked_at=None
        ).count()
        assert active == 0


class TestApi:
    def test_logout_endpoint_clears_cookies(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["user"].id))
        r = client.post(
            "/api/auth/sso/logout",
            json={"saml_provider_id": seeded["saml"].id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        body = r.get_json()
        assert body["revoked_families"] >= 0
        assert body["saml_logout_url"]
        # Cookies cleared (either header absent or with Max-Age=0).
        set_cookies = r.headers.getlist("Set-Cookie")
        lowered = [c.lower() for c in set_cookies]
        assert any(
            "access_token=" in c and ("max-age=0" in c or "expires" in c)
            for c in lowered
        )

    def test_cross_tenant_saml_ignored(self, pg_app, seeded):
        from app.extensions import db
        from app.models.organization import Organization
        from app.models.saml_provider import SamlProvider
        from app.models.user import User

        other = Organization(name="Other SLO", type="company")
        db.session.add(other)
        db.session.flush()
        other_owner = User(
            username="other-slo",
            email="other-slo@example.test",
            is_active=True,
            organization_id=other.id,
        )
        other_owner.set_password("slopassword12345")
        db.session.add(other_owner)
        db.session.flush()
        foreign_saml = SamlProvider(
            organization_id=other.id,
            display_name="Foreign",
            entity_id="https://foreign.example.test/entity",
            sso_url="https://foreign.example.test/sso",
            x509_cert_pem="-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----",
            audience="trustseal-sp-foreign",
            attribute_mapping={
                "email": "email",
                "single_logout_service_url": "https://foreign.example.test/slo",
            },
            is_active=True,
            created_by_id=other_owner.id,
        )
        db.session.add(foreign_saml)
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["user"].id))
        r = client.post(
            "/api/auth/sso/logout",
            json={"saml_provider_id": foreign_saml.id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        # Foreign provider was dropped — no SAML redirect URL.
        assert r.get_json()["saml_logout_url"] is None
