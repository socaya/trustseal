"""Password reset lifecycle (A2).

Covers:

* ``request_reset`` is enumeration-safe: silent on unknown email.
* Issuance revokes prior unconsumed tokens.
* ``consume`` sets the new password and revokes every outstanding
  refresh-token family.
* Replay / expiry / malformed tokens are rejected.
* The HTTP ``/api/auth/password-reset/request`` route always returns
  202 and is rate-limited by IP.
* ``/api/auth/password-reset/<token>/consume`` issues fresh JWT.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest


@pytest.fixture
def _reset_rate_limits(pg_app):
    from app.extensions import db
    from app.models.rate_limit_bucket import RateLimitBucket
    from app.services import rate_limiting

    rate_limiting.clear_cache()
    db.session.query(RateLimitBucket).delete()
    db.session.commit()
    yield


@pytest.fixture
def _clear_outbox(pg_app):
    from app.services import email as mailer

    mailer.clear_outbox()
    yield mailer.outbox()


@pytest.fixture
def user_factory(pg_app):
    from app.extensions import db
    from app.models.user import User

    created = []

    def _factory(**overrides):
        idx = len(created) + 1
        user = User(
            username=overrides.get("username", f"reset-user-{idx}"),
            email=overrides.get("email", f"reset-{idx}@example.test"),
            first_name=overrides.get("first_name", "Rhea"),
            last_name=overrides.get("last_name", "Reset"),
            is_active=overrides.get("is_active", True),
        )
        user.set_password(overrides.get("password", "initialpassword12345"))
        db.session.add(user)
        db.session.flush()
        created.append(user)
        return user

    return _factory


class TestRequestReset:
    def test_unknown_email_is_silent(self, pg_app, _clear_outbox):
        from app.services import password_reset

        out = password_reset.request_reset("nosuch@example.test")
        assert out is None
        assert _clear_outbox == []

    def test_known_email_issues_and_sends(
        self, pg_app, user_factory, _clear_outbox
    ):
        from app.services import password_reset
        from app.models.password_reset_token import PasswordResetToken

        user = user_factory(email="rhea@example.test")
        out = password_reset.request_reset("rhea@example.test", ip="2.3.4.5")
        assert out is not None
        assert out.user_id == user.id
        row = PasswordResetToken.query.filter_by(user_id=user.id).one()
        assert row.consumed_at is None
        assert row.issued_from_ip == "2.3.4.5"
        assert len(_clear_outbox) == 1
        assert _clear_outbox[0].to == "rhea@example.test"
        assert out.raw_token in _clear_outbox[0].body_text

    def test_request_revokes_prior_token(
        self, pg_app, user_factory, _clear_outbox
    ):
        from app.services import password_reset
        from app.models.password_reset_token import PasswordResetToken

        user = user_factory()
        first = password_reset.request_reset(user.email)
        second = password_reset.request_reset(user.email)
        assert first.raw_token != second.raw_token
        active = PasswordResetToken.query.filter_by(
            user_id=user.id, consumed_at=None
        ).count()
        assert active == 1


class TestConsume:
    def test_consume_sets_new_password_and_revokes_sessions(
        self, pg_app, user_factory, _clear_outbox
    ):
        from app.extensions import db
        from app.models.refresh_token import RefreshTokenFamily
        from app.services import password_reset
        from app.services.refresh_tokens import issue_login_tokens

        user = user_factory()
        # Give the user an active refresh family so we can assert it
        # gets revoked on password reset.
        issue_login_tokens(user.id)
        db.session.commit()
        active_before = RefreshTokenFamily.query.filter_by(
            user_id=user.id, revoked_at=None
        ).count()
        assert active_before == 1
        issue = password_reset.request_reset(user.email)
        db.session.commit()
        returned = password_reset.consume(
            issue.raw_token, new_password="brandnewpassword123"
        )
        db.session.commit()
        assert returned.id == user.id
        db.session.refresh(user)
        assert user.check_password("brandnewpassword123")
        assert user.last_password_change_at is not None
        # Every prior refresh family revoked.
        active_after = RefreshTokenFamily.query.filter_by(
            user_id=user.id, revoked_at=None
        ).count()
        assert active_after == 0

    def test_reuse_refused(self, pg_app, user_factory, _clear_outbox):
        from app.extensions import db
        from app.services import password_reset

        user = user_factory()
        issue = password_reset.request_reset(user.email)
        db.session.commit()
        password_reset.consume(
            issue.raw_token, new_password="anotherpassword12345"
        )
        db.session.commit()
        with pytest.raises(password_reset.ResetError) as exc:
            password_reset.consume(
                issue.raw_token, new_password="thirdpassword123"
            )
        assert "consumed" in str(exc.value)

    def test_expired_token_refused(
        self, pg_app, user_factory, _clear_outbox
    ):
        from app.extensions import db
        from app.models.password_reset_token import PasswordResetToken
        from app.services import password_reset

        user = user_factory()
        issue = password_reset.request_reset(user.email)
        db.session.commit()
        row = PasswordResetToken.query.filter_by(user_id=user.id).one()
        row.expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()
        with pytest.raises(password_reset.ResetError) as exc:
            password_reset.consume(
                issue.raw_token, new_password="newfreshpassword123"
            )
        assert "expired" in str(exc.value)

    def test_weak_password_refused(
        self, pg_app, user_factory, _clear_outbox
    ):
        from app.extensions import db
        from app.services import password_reset

        user = user_factory()
        issue = password_reset.request_reset(user.email)
        db.session.commit()
        with pytest.raises(password_reset.ResetError) as exc:
            password_reset.consume(issue.raw_token, new_password="short")
        assert "strength" in str(exc.value)

    def test_same_password_refused(
        self, pg_app, user_factory, _clear_outbox
    ):
        from app.extensions import db
        from app.services import password_reset

        user = user_factory(password="currentpassword12345")
        issue = password_reset.request_reset(user.email)
        db.session.commit()
        with pytest.raises(password_reset.ResetError) as exc:
            password_reset.consume(
                issue.raw_token, new_password="currentpassword12345"
            )
        assert "differ" in str(exc.value)


class TestRequestApi:
    def test_always_returns_202(self, pg_app, _reset_rate_limits, _clear_outbox):
        client = pg_app.test_client()
        # Unknown email.
        r = client.post(
            "/api/auth/password-reset/request",
            json={"email": "ghost@example.test"},
        )
        assert r.status_code == 202
        assert r.get_json()["message"] == "password_reset_email_queued"
        assert _clear_outbox == []

    def test_known_email_triggers_delivery(
        self, pg_app, user_factory, _reset_rate_limits, _clear_outbox
    ):
        user = user_factory()
        client = pg_app.test_client()
        r = client.post(
            "/api/auth/password-reset/request",
            json={"email": user.email},
        )
        assert r.status_code == 202
        assert len(_clear_outbox) == 1
        assert _clear_outbox[0].to == user.email

    def test_rate_limited_by_ip(self, pg_app, _reset_rate_limits, _clear_outbox):
        client = pg_app.test_client()
        for _ in range(5):
            r = client.post(
                "/api/auth/password-reset/request",
                json={"email": "noone@example.test"},
            )
            assert r.status_code == 202
        r = client.post(
            "/api/auth/password-reset/request",
            json={"email": "noone@example.test"},
        )
        assert r.status_code == 429


class TestConsumeApi:
    def test_full_round_trip(
        self, pg_app, user_factory, _reset_rate_limits, _clear_outbox
    ):
        from app.extensions import db
        from app.models.user import User
        from app.services import password_reset

        user = user_factory()
        client = pg_app.test_client()
        r = client.post(
            "/api/auth/password-reset/request",
            json={"email": user.email},
        )
        assert r.status_code == 202
        issue_token = _clear_outbox[0].body_text.rsplit("/", 1)[-1].split()[0].strip()
        r2 = client.post(
            f"/api/auth/password-reset/{issue_token}/consume",
            json={"new_password": "routedbrandnew12345"},
        )
        assert r2.status_code == 200, r2.get_data(as_text=True)
        body = r2.get_json()
        assert "access_token" in body and "refresh_token" in body
        db.session.expire_all()
        refreshed = User.query.filter_by(email=user.email).one()
        assert refreshed.check_password("routedbrandnew12345")

    def test_bad_token_400(self, pg_app):
        client = pg_app.test_client()
        r = client.post(
            "/api/auth/password-reset/short/consume",
            json={"new_password": "validpassword12345"},
        )
        assert r.status_code == 400
