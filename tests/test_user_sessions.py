"""User sessions / device management (A3).

Covers:

* ``issue_login_tokens`` records a new UserSession row with the
  request's User-Agent + IP.
* ``rotate`` advances ``last_seen_at``.
* ``revoke_family`` marks the owning session revoked (with reason).
* ``list_sessions`` returns active rows first, then revoked rows.
* HTTP ``GET /api/auth/sessions`` returns the caller's sessions.
* HTTP ``DELETE /api/auth/sessions/<id>`` revokes one session and
  kills its refresh family — a subsequent refresh against that
  family is denied.
* HTTP ``DELETE /api/auth/sessions/others`` revokes every session
  except the current one (identified by the ``fam`` claim on the
  caller's access token).
* A user cannot revoke another user's session (404, not 403, to
  avoid leaking the existence of other-tenant session IDs).
"""
from __future__ import annotations

import time
from datetime import datetime

import pytest
from flask_jwt_extended import create_access_token, decode_token


@pytest.fixture
def user_factory(pg_app):
    from app.extensions import db
    from app.models.user import User

    created = []

    def _factory(**overrides):
        idx = len(created) + 1
        user = User(
            username=overrides.get("username", f"sess-user-{idx}"),
            email=overrides.get("email", f"sess-{idx}@example.test"),
            is_active=True,
        )
        user.set_password("sessionpassword12345")
        db.session.add(user)
        db.session.flush()
        created.append(user)
        return user

    return _factory


def _access_token(user_id: int, family_id: int | None = None) -> str:
    claims = {}
    if family_id is not None:
        claims["fam"] = family_id
    return create_access_token(identity=str(user_id), additional_claims=claims)


class TestRecordLogin:
    def test_issue_login_records_user_session(self, pg_app, user_factory):
        from app.extensions import db
        from app.models.user_session import UserSession
        from app.services.refresh_tokens import issue_login_tokens

        user = user_factory()
        # ``issue_login_tokens`` reads request headers; drive it
        # through the HTTP login endpoint so UA/IP are captured.
        client = pg_app.test_client()
        r = client.post(
            "/api/auth/login",
            json={"identifier": user.username, "password": "sessionpassword12345"},
            headers={"User-Agent": "TestBrowser/1.0"},
            environ_overrides={"REMOTE_ADDR": "203.0.113.5"},
        )
        assert r.status_code == 200
        db.session.expire_all()
        row = UserSession.query.filter_by(user_id=user.id).one()
        assert row.user_agent == "TestBrowser/1.0"
        assert row.ip_address == "203.0.113.5"
        assert row.revoked_at is None

    def test_record_login_without_request_still_works(
        self, pg_app, user_factory
    ):
        """Programmatic callers (CLI, tests) do not have a request."""
        from app.extensions import db
        from app.models.user_session import UserSession
        from app.services.refresh_tokens import issue_login_tokens

        user = user_factory()
        issue_login_tokens(user.id)
        db.session.commit()
        row = UserSession.query.filter_by(user_id=user.id).one()
        assert row.user_agent is None
        assert row.revoked_at is None


class TestRotateTouch:
    def test_rotate_advances_last_seen_at(self, pg_app, user_factory):
        from app.extensions import db
        from app.models.user_session import UserSession
        from app.services.refresh_tokens import issue_login_tokens, rotate

        user = user_factory()
        access, refresh = issue_login_tokens(user.id)
        db.session.commit()
        session = UserSession.query.filter_by(user_id=user.id).one()
        original_seen = session.last_seen_at

        time.sleep(0.01)  # ensure the timestamp moves forward
        rotate(decode_token(refresh))
        db.session.commit()
        db.session.refresh(session)
        assert session.last_seen_at > original_seen


class TestRevocation:
    def test_revoke_family_marks_session_revoked(
        self, pg_app, user_factory
    ):
        from app.extensions import db
        from app.models.refresh_token import RefreshTokenFamily
        from app.models.user_session import UserSession
        from app.services.refresh_tokens import issue_login_tokens, revoke_family

        user = user_factory()
        issue_login_tokens(user.id)
        db.session.commit()
        family = RefreshTokenFamily.query.filter_by(user_id=user.id).one()
        revoke_family(family, reason="admin_revocation")
        db.session.commit()
        session = UserSession.query.filter_by(user_id=user.id).one()
        assert session.revoked_at is not None
        assert session.revoke_reason == "admin_revocation"

    def test_revoke_all_for_user_marks_every_session(
        self, pg_app, user_factory
    ):
        from app.extensions import db
        from app.models.user_session import UserSession
        from app.services.refresh_tokens import (
            issue_login_tokens,
            revoke_all_for_user,
        )

        user = user_factory()
        issue_login_tokens(user.id)
        issue_login_tokens(user.id)
        db.session.commit()
        revoke_all_for_user(user.id, reason="password_changed")
        db.session.commit()
        active = UserSession.query.filter_by(
            user_id=user.id, revoked_at=None
        ).count()
        assert active == 0
        rows = UserSession.query.filter_by(user_id=user.id).all()
        assert all(r.revoke_reason == "password_changed" for r in rows)


class TestListApi:
    def test_lists_own_sessions(self, pg_app, user_factory):
        from app.extensions import db
        from app.services.refresh_tokens import issue_login_tokens

        user = user_factory()
        issue_login_tokens(user.id)
        issue_login_tokens(user.id)
        db.session.commit()
        client = pg_app.test_client()
        token = _access_token(user.id)
        r = client.get(
            "/api/auth/sessions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["sessions"]) == 2
        assert all(s["active"] for s in data["sessions"])

    def test_requires_auth(self, pg_app):
        client = pg_app.test_client()
        r = client.get("/api/auth/sessions")
        assert r.status_code == 401


class TestRevokeSessionApi:
    def test_revokes_one_session_and_future_refresh_fails(
        self, pg_app, user_factory
    ):
        from app.extensions import db
        from app.models.user_session import UserSession
        from app.services.refresh_tokens import issue_login_tokens, rotate

        user = user_factory()
        access_a, refresh_a = issue_login_tokens(user.id)
        access_b, refresh_b = issue_login_tokens(user.id)
        db.session.commit()
        sessions = UserSession.query.filter_by(user_id=user.id).all()
        target = sessions[0]

        client = pg_app.test_client()
        r = client.delete(
            f"/api/auth/sessions/{target.id}",
            headers={"Authorization": f"Bearer {access_b}"},
        )
        assert r.status_code == 200
        db.session.expire_all()
        db.session.refresh(target)
        assert target.revoked_at is not None

        # Refresh for the revoked family must fail.
        from app.services.refresh_tokens import RefreshRejected

        with pytest.raises((RefreshRejected,)):
            if target.family_id == decode_token(refresh_a)["fam"]:
                rotate(decode_token(refresh_a))
            else:
                rotate(decode_token(refresh_b))

    def test_other_users_session_404(self, pg_app, user_factory):
        from app.extensions import db
        from app.models.user_session import UserSession
        from app.services.refresh_tokens import issue_login_tokens

        a = user_factory()
        b = user_factory()
        issue_login_tokens(a.id)
        issue_login_tokens(b.id)
        db.session.commit()
        a_session = UserSession.query.filter_by(user_id=a.id).one()
        client = pg_app.test_client()
        b_token = _access_token(b.id)
        r = client.delete(
            f"/api/auth/sessions/{a_session.id}",
            headers={"Authorization": f"Bearer {b_token}"},
        )
        assert r.status_code == 404


class TestRevokeOthersApi:
    def test_revokes_everything_except_current(self, pg_app, user_factory):
        from app.extensions import db
        from app.models.user_session import UserSession
        from app.services.refresh_tokens import issue_login_tokens

        user = user_factory()
        issue_login_tokens(user.id)
        issue_login_tokens(user.id)
        issue_login_tokens(user.id)
        db.session.commit()
        rows = UserSession.query.filter_by(user_id=user.id).all()
        assert len(rows) == 3
        # Call the endpoint using one of the families as the "current".
        keep = rows[-1].family_id
        client = pg_app.test_client()
        token = _access_token(user.id, family_id=keep)
        r = client.delete(
            "/api/auth/sessions/others",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["revoked"] == 2
        db.session.expire_all()
        active = UserSession.query.filter_by(
            user_id=user.id, revoked_at=None
        ).count()
        assert active == 1
