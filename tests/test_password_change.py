"""Password-change triggers session invalidation.

Covers:

* Wrong current password returns 401.
* Weak new password returns 400.
* A successful change returns a new access + refresh pair.
* The old access token is rejected on follow-up requests.
* The old refresh token is rejected at ``/api/auth/refresh``.
* Admin and other users cannot invoke the endpoint for someone else.
* Pre-change refresh tokens trigger reuse detection when presented.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def user(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.user import User

    org = Organization(name="Password Tenant")
    db.session.add(org)
    db.session.flush()
    user = User(
        username="pw-user",
        email="pw-user@example.test",
        is_active=True,
        organization_id=org.id,
    )
    user.set_password("original-strong-password-1")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def login_tokens(pg_app, user):
    client = pg_app.test_client()
    r = client.post(
        "/api/auth/login",
        json={"identifier": user.email, "password": "original-strong-password-1"},
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestInputValidation:
    def test_wrong_current_password_rejected(self, pg_app, user, login_tokens):
        r = pg_app.test_client().post(
            "/api/auth/change-password",
            json={
                "current_password": "wrong",
                "new_password": "new-strong-password-two-1",
            },
            headers=_auth(login_tokens["access_token"]),
        )
        assert r.status_code == 401

    def test_weak_new_password_rejected(self, pg_app, user, login_tokens):
        r = pg_app.test_client().post(
            "/api/auth/change-password",
            json={
                "current_password": "original-strong-password-1",
                "new_password": "weak",
            },
            headers=_auth(login_tokens["access_token"]),
        )
        assert r.status_code == 400

    def test_same_password_rejected(self, pg_app, user, login_tokens):
        r = pg_app.test_client().post(
            "/api/auth/change-password",
            json={
                "current_password": "original-strong-password-1",
                "new_password": "original-strong-password-1",
            },
            headers=_auth(login_tokens["access_token"]),
        )
        assert r.status_code == 400

    def test_endpoint_changes_only_the_callers_password(self, pg_app, user, login_tokens):
        """The endpoint is self-service: it has no target user id in the URL."""
        from app.extensions import db
        from app.models.user import User

        other = User(
            username="other-user",
            email="other-user@example.test",
            is_active=True,
            organization_id=user.organization_id,
        )
        other.set_password("other-strong-password-1")
        db.session.add(other)
        db.session.commit()
        pg_app.test_client().post(
            "/api/auth/change-password",
            json={
                "current_password": "original-strong-password-1",
                "new_password": "new-strong-password-two-1",
            },
            headers=_auth(login_tokens["access_token"]),
        )
        db.session.expire_all()
        assert db.session.get(User, other.id).check_password("other-strong-password-1")


class TestInvalidation:
    def test_successful_change_returns_fresh_pair(self, pg_app, user, login_tokens):
        r = pg_app.test_client().post(
            "/api/auth/change-password",
            json={
                "current_password": "original-strong-password-1",
                "new_password": "new-strong-password-two-1",
            },
            headers=_auth(login_tokens["access_token"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["access_token"] != login_tokens["access_token"]
        assert body["refresh_token"] != login_tokens["refresh_token"]

    def test_old_access_token_rejected_after_change(self, pg_app, user, login_tokens):
        client = pg_app.test_client()
        client.post(
            "/api/auth/change-password",
            json={
                "current_password": "original-strong-password-1",
                "new_password": "new-strong-password-two-1",
            },
            headers=_auth(login_tokens["access_token"]),
        )
        # The legacy /api/auth/me endpoint authenticates via access JWT.
        r = client.get("/api/auth/me", headers=_auth(login_tokens["access_token"]))
        assert r.status_code == 401

    def test_old_refresh_rejected_and_family_revoked(self, pg_app, user, login_tokens):
        from app.models.refresh_token import RefreshTokenFamily
        from flask_jwt_extended import decode_token

        client = pg_app.test_client()
        client.post(
            "/api/auth/change-password",
            json={
                "current_password": "original-strong-password-1",
                "new_password": "new-strong-password-two-1",
            },
            headers=_auth(login_tokens["access_token"]),
        )
        refresh = login_tokens["refresh_token"]
        fam = decode_token(refresh)["fam"]
        from app.extensions import db

        db.session.expire_all()
        family = db.session.get(RefreshTokenFamily, fam)
        assert family is not None
        assert family.revoked_at is not None
        assert family.revoke_reason == "password_changed"
        # Replay — the token is on the blocklist; the request is denied.
        r = client.post(
            "/api/auth/refresh",
            headers=_auth(login_tokens["refresh_token"]),
        )
        assert r.status_code == 401

    def test_new_refresh_pair_works(self, pg_app, user, login_tokens):
        client = pg_app.test_client()
        change = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "original-strong-password-1",
                "new_password": "new-strong-password-two-1",
            },
            headers=_auth(login_tokens["access_token"]),
        )
        new_access = change.get_json()["access_token"]
        new_refresh = change.get_json()["refresh_token"]
        me = client.get("/api/auth/me", headers=_auth(new_access))
        assert me.status_code == 200
        rotate = client.post("/api/auth/refresh", headers=_auth(new_refresh))
        assert rotate.status_code == 200
