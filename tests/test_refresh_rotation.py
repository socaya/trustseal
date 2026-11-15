"""Refresh-token family rotation and reuse-detection contract.

Covers:

* Login/register issues a refresh token carrying a ``fam`` claim.
* Rotation issues a new refresh and marks the old jti revoked.
* The old refresh jti is rejected on a second redemption attempt and
  the entire family is revoked.
* A revoked family's access tokens emit a ``refresh.reuse_detected``
  security event.
* ``revoke_all_for_user`` marks every active family revoked and adds
  :class:`RevokedToken` rows so subsequent presentations fail.
"""
from __future__ import annotations

import pytest
from flask_jwt_extended import decode_token


@pytest.fixture
def user(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.user import User

    org = Organization(name="Refresh Tenant")
    db.session.add(org)
    db.session.flush()
    user = User(
        username="refresher",
        email="refresher@example.test",
        is_active=True,
        organization_id=org.id,
    )
    user.set_password("not-used-strong-password")
    db.session.add(user)
    db.session.commit()
    return user


def _decode(token: str) -> dict:
    return decode_token(token)


class TestIssueOnLogin:
    def test_login_includes_family_claim(self, pg_app, user):
        client = pg_app.test_client()
        r = client.post(
            "/api/auth/login",
            json={"identifier": user.email, "password": "not-used-strong-password"},
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        refresh = r.get_json()["refresh_token"]
        payload = _decode(refresh)
        assert "fam" in payload
        assert isinstance(payload["fam"], int)

    def test_each_login_starts_a_new_family(self, pg_app, user):
        client = pg_app.test_client()
        r1 = client.post(
            "/api/auth/login",
            json={"identifier": user.email, "password": "not-used-strong-password"},
        )
        r2 = client.post(
            "/api/auth/login",
            json={"identifier": user.email, "password": "not-used-strong-password"},
        )
        fam_1 = _decode(r1.get_json()["refresh_token"])["fam"]
        fam_2 = _decode(r2.get_json()["refresh_token"])["fam"]
        assert fam_1 != fam_2


class TestRotation:
    def test_rotate_issues_new_refresh_same_family(self, pg_app, user):
        client = pg_app.test_client()
        login = client.post(
            "/api/auth/login",
            json={"identifier": user.email, "password": "not-used-strong-password"},
        )
        first_refresh = login.get_json()["refresh_token"]
        first_fam = _decode(first_refresh)["fam"]
        refresh_resp = client.post(
            "/api/auth/refresh",
            headers={"Authorization": f"Bearer {first_refresh}"},
        )
        assert refresh_resp.status_code == 200
        second_refresh = refresh_resp.get_json()["refresh_token"]
        assert _decode(second_refresh)["fam"] == first_fam
        assert _decode(second_refresh)["jti"] != _decode(first_refresh)["jti"]

    def test_reuse_of_old_jti_revokes_entire_family(self, pg_app, user):
        client = pg_app.test_client()
        login = client.post(
            "/api/auth/login",
            json={"identifier": user.email, "password": "not-used-strong-password"},
        )
        first = login.get_json()["refresh_token"]
        # Rotate once; now ``first`` is revoked and ``second`` is live.
        rotate_resp = client.post(
            "/api/auth/refresh",
            headers={"Authorization": f"Bearer {first}"},
        )
        assert rotate_resp.status_code == 200
        second = rotate_resp.get_json()["refresh_token"]
        # Replay the first token — this MUST trigger reuse detection.
        from app.models.refresh_token import RefreshTokenFamily

        first_fam = _decode(first)["fam"]
        replay = client.post(
            "/api/auth/refresh",
            headers={"Authorization": f"Bearer {first}"},
        )
        assert replay.status_code == 401
        # Reuse detection happens inside the JWT blocklist callback;
        # the family must now be marked revoked.
        from app.extensions import db

        db.session.expire_all()
        family = db.session.get(RefreshTokenFamily, first_fam)
        assert family is not None
        assert family.revoked_at is not None
        assert family.revoke_reason == "reuse_detected"
        # The second refresh must also be unusable because the family
        # was revoked by the replay attempt.
        follow_up = client.post(
            "/api/auth/refresh",
            headers={"Authorization": f"Bearer {second}"},
        )
        assert follow_up.status_code == 401

    def test_rotation_emits_revoked_token_row_for_old_jti(self, pg_app, user):
        from app.models.revoked_token import RevokedToken

        client = pg_app.test_client()
        login = client.post(
            "/api/auth/login",
            json={"identifier": user.email, "password": "not-used-strong-password"},
        )
        first = login.get_json()["refresh_token"]
        first_jti = _decode(first)["jti"]
        client.post(
            "/api/auth/refresh",
            headers={"Authorization": f"Bearer {first}"},
        )
        assert RevokedToken.query.filter_by(jti=first_jti).first() is not None


class TestServiceDirectCalls:
    def test_revoke_all_for_user(self, pg_app, user):
        from app.services.refresh_tokens import (
            issue_login_tokens,
            revoke_all_for_user,
        )
        from app.models.refresh_token import RefreshTokenFamily

        issue_login_tokens(user.id)
        issue_login_tokens(user.id)
        from app.extensions import db
        db.session.commit()
        revoked = revoke_all_for_user(user.id, reason="password_change")
        db.session.commit()
        assert revoked == 2
        assert (
            RefreshTokenFamily.query.filter_by(user_id=user.id, revoked_at=None).count()
            == 0
        )

    def test_reuse_detection_emits_security_event(self, pg_app, user):
        from app.extensions import db
        from app.models.event_delivery import SecurityEvent
        from app.services.refresh_tokens import (
            ReuseDetected,
            issue_login_tokens,
            rotate,
        )

        _access, refresh = issue_login_tokens(user.id)
        db.session.commit()
        first_payload = decode_token(refresh)
        rotate(first_payload)
        db.session.commit()
        with pytest.raises(ReuseDetected):
            rotate(first_payload)
        db.session.commit()
        event = (
            SecurityEvent.query.filter(
                SecurityEvent.actor_id == user.id,
                SecurityEvent.action.like("refresh.%"),
            )
            .order_by(SecurityEvent.id.desc())
            .first()
        )
        assert event is not None
        assert event.action == "refresh.reuse_detected"
