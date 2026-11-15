"""Email verification lifecycle (A1).

Covers:

* ``issue`` creates a hashed token, delivers a memory-transport email
  with the verify URL, and marks prior unconsumed tokens consumed.
* ``consume`` succeeds once, flips ``email_verified`` + stamps
  ``email_verified_at``, and refuses on reuse / expiry / mismatched
  email.
* ``register`` on the HTTP API sends the verification email and
  returns ``email_verified=False``.
* ``verify-email/<token>`` endpoint flips the user to verified.
* ``verify-email/resend`` is rate-limited and refuses once already
  verified.
* ``require_verified_email`` decorator admits verified callers and
  blocks unverified ones with 403.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token


@pytest.fixture
def _reset_rate_limits(pg_app):
    """Avoid cross-test contamination for the resend rate bucket."""
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
            username=overrides.get("username", f"verify-user-{idx}"),
            email=overrides.get("email", f"verify-{idx}@example.test"),
            first_name=overrides.get("first_name", "Vera"),
            last_name=overrides.get("last_name", "Verifier"),
            is_active=overrides.get("is_active", True),
        )
        user.set_password(overrides.get("password", "testpassword12345"))
        db.session.add(user)
        db.session.flush()
        created.append(user)
        return user

    return _factory


class TestIssue:
    def test_issues_token_and_sends_email(
        self, pg_app, user_factory, _clear_outbox
    ):
        from app.services import email_verification
        from app.models.email_verification_token import EmailVerificationToken

        user = user_factory()
        result = email_verification.issue(user, ip="1.2.3.4")
        assert result.user_id == user.id
        assert isinstance(result.raw_token, str)
        assert len(result.raw_token) >= 32
        # The raw token must never land in the DB.
        row = EmailVerificationToken.query.filter_by(user_id=user.id).one()
        assert row.token_sha256 != result.raw_token
        assert row.consumed_at is None
        assert row.email == user.email
        assert row.issued_from_ip == "1.2.3.4"
        assert len(_clear_outbox) == 1
        msg = _clear_outbox[0]
        assert msg.to == user.email
        assert result.raw_token in msg.body_text
        assert msg.body_html and result.raw_token in msg.body_html

    def test_second_issue_revokes_prior_token(
        self, pg_app, user_factory, _clear_outbox
    ):
        from app.services import email_verification
        from app.models.email_verification_token import EmailVerificationToken

        user = user_factory()
        first = email_verification.issue(user)
        second = email_verification.issue(user)
        assert first.raw_token != second.raw_token
        active = EmailVerificationToken.query.filter_by(
            user_id=user.id, consumed_at=None
        ).count()
        assert active == 1
        consumed = EmailVerificationToken.query.filter(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.consumed_at.isnot(None),
        ).count()
        assert consumed == 1

    def test_issue_refuses_already_verified(
        self, pg_app, user_factory, _clear_outbox
    ):
        from app.services import email_verification
        from app.extensions import db

        user = user_factory()
        user.email_verified = True
        db.session.commit()
        with pytest.raises(email_verification.VerificationError):
            email_verification.issue(user)


class TestConsume:
    def test_consumes_and_flips_user(self, pg_app, user_factory, _clear_outbox):
        from app.extensions import db
        from app.services import email_verification

        user = user_factory()
        result = email_verification.issue(user)
        db.session.commit()
        returned = email_verification.consume(result.raw_token)
        db.session.commit()
        assert returned.id == user.id
        db.session.refresh(user)
        assert user.email_verified is True
        assert user.email_verified_at is not None

    def test_reuse_refused(self, pg_app, user_factory, _clear_outbox):
        from app.extensions import db
        from app.services import email_verification

        user = user_factory()
        result = email_verification.issue(user)
        db.session.commit()
        email_verification.consume(result.raw_token)
        db.session.commit()
        with pytest.raises(email_verification.VerificationError) as exc:
            email_verification.consume(result.raw_token)
        assert "consumed" in str(exc.value)

    def test_expired_token_refused(
        self, pg_app, user_factory, _clear_outbox
    ):
        from app.extensions import db
        from app.services import email_verification
        from app.models.email_verification_token import EmailVerificationToken

        user = user_factory()
        result = email_verification.issue(user)
        db.session.commit()
        row = EmailVerificationToken.query.filter_by(user_id=user.id).one()
        row.expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()
        with pytest.raises(email_verification.VerificationError) as exc:
            email_verification.consume(result.raw_token)
        assert "expired" in str(exc.value)

    def test_email_changed_refused(
        self, pg_app, user_factory, _clear_outbox
    ):
        from app.extensions import db
        from app.services import email_verification

        user = user_factory()
        result = email_verification.issue(user)
        db.session.commit()
        user.email = "different@example.test"
        db.session.commit()
        with pytest.raises(email_verification.VerificationError) as exc:
            email_verification.consume(result.raw_token)
        assert "email_changed" in str(exc.value)

    def test_unknown_token_refused(self, pg_app):
        from app.services import email_verification

        with pytest.raises(email_verification.VerificationError):
            email_verification.consume("not-a-real-token-12345678901234567890")

    def test_malformed_token_refused(self, pg_app):
        from app.services import email_verification

        with pytest.raises(email_verification.VerificationError):
            email_verification.consume("short")


class TestRegisterApi:
    def test_register_sends_email_and_returns_unverified(
        self, pg_app, _clear_outbox
    ):
        client = pg_app.test_client()
        r = client.post(
            "/api/auth/register",
            json={
                "username": "newcomer",
                "email": "newcomer@example.test",
                "password": "testpassword12345",
            },
        )
        assert r.status_code == 201, r.get_data(as_text=True)
        data = r.get_json()
        assert data["email_verified"] is False
        assert len(_clear_outbox) == 1
        assert _clear_outbox[0].to == "newcomer@example.test"

    def test_verify_endpoint_flips_user(self, pg_app, _clear_outbox):
        from app.extensions import db
        from app.models.user import User
        from app.services import email_verification

        client = pg_app.test_client()
        r = client.post(
            "/api/auth/register",
            json={
                "username": "verifier2",
                "email": "verifier2@example.test",
                "password": "testpassword12345",
            },
        )
        assert r.status_code == 201
        # Snatch the token from the memory outbox by re-issuing.
        # (The register call already issued; grab from the email.)
        msg = _clear_outbox[0]
        # The token is the last URL segment in the mail body.
        token = msg.body_text.rsplit("/", 1)[-1].split()[0].strip()
        r2 = client.post(f"/api/auth/verify-email/{token}")
        assert r2.status_code == 200, r2.get_data(as_text=True)
        user = User.query.filter_by(email="verifier2@example.test").one()
        assert user.email_verified is True

    def test_verify_bad_token_400(self, pg_app):
        client = pg_app.test_client()
        r = client.post(
            "/api/auth/verify-email/not-a-real-token-" + "a" * 32
        )
        assert r.status_code == 400


class TestResendApi:
    def test_resend_requires_auth(self, pg_app):
        client = pg_app.test_client()
        r = client.post("/api/auth/verify-email/resend")
        assert r.status_code == 401

    def test_resend_rate_limited(
        self, pg_app, user_factory, _clear_outbox, _reset_rate_limits
    ):
        user = user_factory()
        client = pg_app.test_client()
        token = create_access_token(identity=str(user.id))
        headers = {"Authorization": f"Bearer {token}"}
        for _ in range(3):
            r = client.post("/api/auth/verify-email/resend", headers=headers)
            assert r.status_code == 200
        r = client.post("/api/auth/verify-email/resend", headers=headers)
        assert r.status_code == 429
        assert r.get_json()["error"] == "rate_limited"

    def test_resend_refuses_when_already_verified(
        self, pg_app, user_factory, _reset_rate_limits
    ):
        from app.extensions import db

        user = user_factory()
        user.email_verified = True
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(user.id))
        headers = {"Authorization": f"Bearer {token}"}
        r = client.post("/api/auth/verify-email/resend", headers=headers)
        assert r.status_code == 400


class TestDecorator:
    def test_rejects_unverified_api_caller(self, pg_app, user_factory):
        user = user_factory()
        client = pg_app.test_client()
        token = create_access_token(identity=str(user.id))
        r = client.get(
            "/api/_test/verified-only",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403
        assert r.get_json()["error"] == "email_not_verified"

    def test_admits_verified_api_caller(self, pg_app, user_factory):
        from app.extensions import db

        user = user_factory()
        user.email_verified = True
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(user.id))
        r = client.get(
            "/api/_test/verified-only",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200

    def test_rejects_anonymous(self, pg_app):
        client = pg_app.test_client()
        r = client.get("/api/_test/verified-only")
        # The API gate (api_access policy) rejects unauthenticated
        # /api callers with 401 before the decorator even runs. Both
        # 401 (gate) and 403 (decorator) are acceptable: the anonymous
        # caller is denied either way.
        assert r.status_code in {401, 403}
