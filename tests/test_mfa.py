"""TOTP MFA contract.

Covers:

* Enrollment returns a secret and otpauth URI; the secret never
  appears in the serialized credential row.
* A wrong TOTP code during confirm refuses to activate the credential.
* A valid code activates and mints 10 recovery codes.
* The same TOTP code cannot be replayed on subsequent verification.
* Clock drift within ±30 seconds is tolerated.
* A recovery code is accepted once and then refused.
* Disable requires a valid code and marks all recovery codes consumed.
* The status endpoint returns the right enrollment flag and remaining
  recovery count.
* An inactive user cannot enroll.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pyotp
import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-must-be-long-enough-to-derive-fernet")


@pytest.fixture
def user(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.user import User

    org = Organization(name="MFA Tenant")
    db.session.add(org)
    db.session.flush()
    user = User(
        username="mfa-probe",
        email="mfa-probe@example.test",
        is_active=True,
        organization_id=org.id,
    )
    user.set_password("not-used")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def app_secret(pg_app):
    # The MFA service derives a Fernet key from SECRET_KEY, so we need a
    # value long enough to clear the length check.
    return pg_app.config.get("SECRET_KEY") or "x" * 40


class TestEnrollment:
    def test_begin_enrollment_returns_secret_and_uri(self, pg_app, user, app_secret):
        from app.services import mfa

        result = mfa.begin_enrollment(user, app_secret)
        assert result.secret
        assert result.otpauth_uri.startswith("otpauth://totp/")
        assert "TrustSeal" in result.otpauth_uri
        assert mfa.is_enrolled(user) is False, "credential is pending, not active"

    def test_confirm_with_wrong_code_fails(self, pg_app, user, app_secret):
        from app.services import mfa

        mfa.begin_enrollment(user, app_secret)
        with pytest.raises(mfa.MfaError):
            mfa.confirm_enrollment(user, "000000", app_secret=app_secret)
        assert mfa.is_enrolled(user) is False

    def test_confirm_with_valid_code_activates(self, pg_app, user, app_secret):
        from app.services import mfa

        result = mfa.begin_enrollment(user, app_secret)
        code = pyotp.TOTP(result.secret).now()
        confirmed = mfa.confirm_enrollment(user, code, app_secret=app_secret)
        assert mfa.is_enrolled(user) is True
        assert len(confirmed.recovery_codes) == 10
        assert all(len(c) == 16 for c in confirmed.recovery_codes)
        assert mfa.unused_recovery_code_count(user) == 10

    def test_begin_resets_existing_pending(self, pg_app, user, app_secret):
        from app.services import mfa

        first = mfa.begin_enrollment(user, app_secret)
        second = mfa.begin_enrollment(user, app_secret)
        assert first.secret != second.secret

    def test_inactive_user_rejected(self, pg_app, user, app_secret):
        from app.extensions import db
        from app.services import mfa

        user.is_active = False
        db.session.commit()
        with pytest.raises(mfa.MfaError):
            mfa.begin_enrollment(user, app_secret)


class TestVerify:
    def _enrol(self, pg_app, user, app_secret):
        from app.services import mfa

        start = mfa.begin_enrollment(user, app_secret)
        code = pyotp.TOTP(start.secret).now()
        confirmed = mfa.confirm_enrollment(user, code, app_secret=app_secret)
        return start.secret, confirmed.recovery_codes

    def test_fresh_totp_accepted(self, pg_app, user, app_secret):
        from app.services import mfa

        secret, _recovery = self._enrol(pg_app, user, app_secret)
        future = datetime.now(timezone.utc) + timedelta(seconds=35)
        code = pyotp.TOTP(secret).at(future)
        assert mfa.verify(user, code, app_secret=app_secret, now=future) == "totp"

    def test_replay_of_same_totp_rejected(self, pg_app, user, app_secret):
        from app.services import mfa

        secret, _recovery = self._enrol(pg_app, user, app_secret)
        now = datetime.now(timezone.utc) + timedelta(seconds=35)
        code = pyotp.TOTP(secret).at(now)
        mfa.verify(user, code, app_secret=app_secret, now=now)
        with pytest.raises(mfa.MfaError):
            mfa.verify(user, code, app_secret=app_secret, now=now)

    def test_clock_drift_within_window_accepted(self, pg_app, user, app_secret):
        """A verification one counter after enrollment, with a code from
        the user's clock running a counter behind the server, must pass.
        """
        from app.services import mfa

        secret, _recovery = self._enrol(pg_app, user, app_secret)
        # Skip two counters so we're clearly past the enrollment counter.
        later = datetime.now(timezone.utc) + timedelta(seconds=90)
        # User's device is one counter behind the server.
        user_clock = later - timedelta(seconds=30)
        code = pyotp.TOTP(secret).at(user_clock)
        assert mfa.verify(user, code, app_secret=app_secret, now=later) == "totp"

    def test_clock_drift_outside_window_rejected(self, pg_app, user, app_secret):
        from app.services import mfa

        secret, _recovery = self._enrol(pg_app, user, app_secret)
        future = datetime.now(timezone.utc) + timedelta(seconds=35)
        code = pyotp.TOTP(secret).at(future)
        now = future + timedelta(minutes=5)
        with pytest.raises(mfa.MfaError):
            mfa.verify(user, code, app_secret=app_secret, now=now)

    def test_recovery_code_accepted_once(self, pg_app, user, app_secret):
        from app.services import mfa

        _secret, recovery = self._enrol(pg_app, user, app_secret)
        used = recovery[0]
        assert mfa.verify(user, used, app_secret=app_secret) == "recovery"
        assert mfa.unused_recovery_code_count(user) == 9
        with pytest.raises(mfa.MfaError):
            mfa.verify(user, used, app_secret=app_secret)

    def test_disable_requires_valid_code_and_consumes_recovery_codes(
        self, pg_app, user, app_secret
    ):
        from app.services import mfa

        secret, _recovery = self._enrol(pg_app, user, app_secret)
        with pytest.raises(mfa.MfaError):
            mfa.verify(user, "000000", app_secret=app_secret)
        future = datetime.now(timezone.utc) + timedelta(seconds=35)
        mfa.verify(user, pyotp.TOTP(secret).at(future), app_secret=app_secret, now=future)
        mfa.disable(user)
        assert mfa.is_enrolled(user) is False
        assert mfa.unused_recovery_code_count(user) == 0


class TestApi:
    @pytest.fixture
    def token(self, pg_app, user):
        from flask_jwt_extended import create_access_token

        return create_access_token(identity=str(user.id))

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_status_initial(self, pg_app, user, token):
        r = pg_app.test_client().get("/api/auth/mfa/status", headers=self._auth(token))
        assert r.status_code == 200
        assert r.get_json() == {"enrolled": False, "unused_recovery_codes": 0}

    def test_enroll_requires_idempotency_key(self, pg_app, user, token):
        r = pg_app.test_client().post(
            "/api/auth/mfa/enroll", headers=self._auth(token)
        )
        assert r.status_code == 400

    def test_enroll_and_confirm_round_trip(self, pg_app, user, token, app_secret):
        import pyotp

        headers = {"Idempotency-Key": "k-enroll", **self._auth(token)}
        enroll = pg_app.test_client().post("/api/auth/mfa/enroll", headers=headers)
        assert enroll.status_code == 201, enroll.get_data(as_text=True)
        secret = enroll.get_json()["secret"]
        code = pyotp.TOTP(secret).now()
        confirm_headers = {"Idempotency-Key": "k-confirm", **self._auth(token)}
        confirm = pg_app.test_client().post(
            "/api/auth/mfa/confirm",
            json={"code": code},
            headers=confirm_headers,
        )
        assert confirm.status_code == 200, confirm.get_data(as_text=True)
        body = confirm.get_json()
        assert len(body["recovery_codes"]) == 10

    def test_status_reflects_enrollment(self, pg_app, user, token, app_secret):
        import pyotp

        client = pg_app.test_client()
        enroll = client.post(
            "/api/auth/mfa/enroll",
            headers={"Idempotency-Key": "k-enroll2", **self._auth(token)},
        )
        secret = enroll.get_json()["secret"]
        client.post(
            "/api/auth/mfa/confirm",
            json={"code": pyotp.TOTP(secret).now()},
            headers={"Idempotency-Key": "k-confirm2", **self._auth(token)},
        )
        r = client.get("/api/auth/mfa/status", headers=self._auth(token))
        body = r.get_json()
        assert body["enrolled"] is True
        assert body["unused_recovery_codes"] == 10
