"""MFA secret re-wrap under new SECRET_KEY (L2)."""
from __future__ import annotations

import pyotp
import pytest


@pytest.fixture
def enrolled(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.user import User
    from app.services import mfa

    org = Organization(name="Rewrap Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    user = User(
        username="rewrap-user",
        email="rewrap-user@example.test",
        is_active=True,
        organization_id=org.id,
    )
    user.set_password("rewrappassword12345")
    db.session.add(user)
    db.session.flush()
    enrollment = mfa.begin_enrollment(user, app_secret=pg_app.config["SECRET_KEY"])
    code = pyotp.TOTP(enrollment.secret).now()
    mfa.confirm_enrollment(user, code, app_secret=pg_app.config["SECRET_KEY"])
    db.session.commit()
    return {"user": user, "secret": enrollment.secret}


class TestDualKeyRead:
    def test_old_cipher_decrypts_with_previous_key(
        self, pg_app, enrolled
    ):
        """After rotation, the stored cipher still decrypts via the old key."""
        from app.extensions import db
        from app.models.mfa import MfaCredential
        from app.services import mfa

        prior = pg_app.config["SECRET_KEY"]
        # Rotate: new current, previous retained for compatibility.
        new_secret = "new-rotated-secret-must-be-at-least-32-chars"
        pg_app.config["SECRET_KEY"] = new_secret
        pg_app.config["MFA_PREVIOUS_SECRET_KEYS"] = [prior]
        try:
            credential = MfaCredential.query.filter_by(
                user_id=enrolled["user"].id
            ).one()
            # Direct decrypt call returns the original seed without
            # raising even though the cipher was written under the
            # previous key.
            seed = mfa._decrypt(credential.secret_cipher, new_secret)
            assert seed == enrolled["secret"]
        finally:
            pg_app.config["SECRET_KEY"] = prior
            pg_app.config["MFA_PREVIOUS_SECRET_KEYS"] = []


class TestRewrap:
    def test_rewraps_everything_under_new_key(self, pg_app, enrolled):
        from app.extensions import db
        from app.models.mfa import MfaCredential
        from app.services import mfa

        prior = pg_app.config["SECRET_KEY"]
        new_secret = "another-rotated-secret-at-least-thirty-two"
        pg_app.config["SECRET_KEY"] = new_secret
        pg_app.config["MFA_PREVIOUS_SECRET_KEYS"] = [prior]
        try:
            old_cipher = (
                MfaCredential.query.filter_by(user_id=enrolled["user"].id)
                .one()
                .secret_cipher
            )
            summary = mfa.rewrap_all(current_secret=new_secret)
            db.session.commit()
            assert summary["rewrapped"] >= 1
            refreshed = (
                MfaCredential.query.filter_by(user_id=enrolled["user"].id).one()
            )
            assert refreshed.secret_cipher != old_cipher
            # After rewrap, the active key alone decrypts.
            pg_app.config["MFA_PREVIOUS_SECRET_KEYS"] = []
            seed = mfa._decrypt(refreshed.secret_cipher, new_secret)
            assert seed == enrolled["secret"]
        finally:
            pg_app.config["SECRET_KEY"] = prior
            pg_app.config["MFA_PREVIOUS_SECRET_KEYS"] = []

    def test_summary_counts_fields(self, pg_app, enrolled):
        from app.services import mfa

        summary = mfa.rewrap_all(current_secret=pg_app.config["SECRET_KEY"])
        assert set(summary) == {"rewrapped", "already_current", "failed"}
        # Fernet ciphertext is non-deterministic (fresh IV every
        # encryption), so running rewrap always counts as a fresh
        # write even when the key is unchanged. That is the correct
        # security property — the operation is idempotent at the
        # plaintext level, not the cipher level.
        assert summary["rewrapped"] + summary["already_current"] >= 1
        assert summary["failed"] == 0
