"""Step-up MFA on high-risk actions (A4).

Covers:

* Caller without MFA enrolled hits 412 ``mfa_enrollment_required`` on
  a decorated route.
* Caller with MFA enrolled but no recent proof hits 403
  ``step_up_required`` pointing at ``/api/auth/mfa/step-up``.
* ``POST /api/auth/mfa/step-up`` with a valid TOTP returns a fresh
  access token carrying ``mfa_verified_at``.
* The old access token is revoked (listed in ``revoked_tokens``).
* The new access token admits the caller to the decorated route.
* Submitting a wrong TOTP to step-up returns 401.
* An expired ``mfa_verified_at`` (older than max_age_seconds) is
  refused.
"""
from __future__ import annotations

import time

import pyotp
import pytest
from flask_jwt_extended import create_access_token


@pytest.fixture
def user_factory(pg_app):
    from app.extensions import db
    from app.models.user import User

    created = []

    def _factory(**overrides):
        idx = len(created) + 1
        user = User(
            username=overrides.get("username", f"mfa-user-{idx}"),
            email=overrides.get("email", f"mfa-{idx}@example.test"),
            is_active=True,
        )
        user.set_password("stepuppassword12345")
        db.session.add(user)
        db.session.flush()
        created.append(user)
        return user

    return _factory


@pytest.fixture
def enrolled_user(pg_app, user_factory):
    """Return (user, totp_secret) with MFA enrolled and activated.

    Resets ``last_counter`` to 0 after confirmation so the same
    counter window can be exercised inside the test body. The service
    refuses to verify a counter less-or-equal to the previously used
    one (replay protection); without this reset the test would have
    to sleep 30+ seconds.
    """
    from app.extensions import db
    from app.models.mfa import MfaCredential
    from app.services import mfa as mfa_svc

    user = user_factory()
    enrollment = mfa_svc.begin_enrollment(user, app_secret=pg_app.config["SECRET_KEY"])
    secret = enrollment.secret
    code = pyotp.TOTP(secret).now()
    mfa_svc.confirm_enrollment(user, code, app_secret=pg_app.config["SECRET_KEY"])
    MfaCredential.query.filter_by(user_id=user.id).update({"last_counter": 0})
    db.session.commit()
    return user, secret


class TestDecoratorGates:
    def test_rejects_without_mfa_enrolled(self, pg_app, user_factory):
        user = user_factory()
        client = pg_app.test_client()
        token = create_access_token(identity=str(user.id))
        r = client.post(
            "/api/_test/step-up-only",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 412
        body = r.get_json()
        assert body["mfa_enrollment_required"] is True

    def test_rejects_without_recent_mfa(self, pg_app, enrolled_user):
        user, _secret = enrolled_user
        client = pg_app.test_client()
        token = create_access_token(identity=str(user.id))
        r = client.post(
            "/api/_test/step-up-only",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403
        body = r.get_json()
        assert body["step_up_required"] is True
        assert body["step_up_url"] == "/api/auth/mfa/step-up"

    def test_rejects_stale_mfa_verified_at(self, pg_app, enrolled_user):
        user, _secret = enrolled_user
        stale = int(time.time()) - 3600  # one hour ago
        token = create_access_token(
            identity=str(user.id),
            additional_claims={"mfa_verified_at": stale},
        )
        client = pg_app.test_client()
        r = client.post(
            "/api/_test/step-up-only",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    def test_admits_recent_mfa(self, pg_app, enrolled_user):
        user, _secret = enrolled_user
        token = create_access_token(
            identity=str(user.id),
            additional_claims={"mfa_verified_at": int(time.time())},
        )
        client = pg_app.test_client()
        r = client.post(
            "/api/_test/step-up-only",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.get_json()["ok"] is True


class TestStepUpApi:
    def test_step_up_returns_fresh_access_token(
        self, pg_app, enrolled_user
    ):
        from app.extensions import db
        from app.models.revoked_token import RevokedToken
        from flask_jwt_extended import decode_token

        user, secret = enrolled_user
        original = create_access_token(identity=str(user.id))
        client = pg_app.test_client()
        totp = pyotp.TOTP(secret).now()
        r = client.post(
            "/api/auth/mfa/step-up",
            json={"code": totp},
            headers={"Authorization": f"Bearer {original}"},
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        body = r.get_json()
        new_access = body["access_token"]
        assert new_access != original
        # New access token carries mfa_verified_at.
        payload = decode_token(new_access)
        assert payload["mfa_verified_at"] > 0
        # Original access token was revoked.
        original_jti = decode_token(original)["jti"]
        assert db.session.get(RevokedToken, original_jti) is not None

    def test_step_up_then_decorated_route_admits(
        self, pg_app, enrolled_user
    ):
        user, secret = enrolled_user
        original = create_access_token(identity=str(user.id))
        client = pg_app.test_client()
        totp = pyotp.TOTP(secret).now()
        r = client.post(
            "/api/auth/mfa/step-up",
            json={"code": totp},
            headers={"Authorization": f"Bearer {original}"},
        )
        assert r.status_code == 200
        new_access = r.get_json()["access_token"]
        r2 = client.post(
            "/api/_test/step-up-only",
            headers={"Authorization": f"Bearer {new_access}"},
        )
        assert r2.status_code == 200

    def test_step_up_wrong_code_401(self, pg_app, enrolled_user):
        user, _secret = enrolled_user
        original = create_access_token(identity=str(user.id))
        client = pg_app.test_client()
        r = client.post(
            "/api/auth/mfa/step-up",
            json={"code": "000000"},
            headers={"Authorization": f"Bearer {original}"},
        )
        assert r.status_code == 401

    def test_step_up_without_enrollment_412(
        self, pg_app, user_factory
    ):
        user = user_factory()
        client = pg_app.test_client()
        token = create_access_token(identity=str(user.id))
        r = client.post(
            "/api/auth/mfa/step-up",
            json={"code": "123456"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 412
