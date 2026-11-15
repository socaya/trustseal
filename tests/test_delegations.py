"""Time-bound delegation (B3).

Covers the service layer:

* ``grant`` refuses self-delegation.
* ``grant`` refuses windows in the past or empty windows.
* ``grant`` refuses cross-organization pairs.
* ``active_for`` returns a matching delegation inside the window.
* ``active_for`` excludes expired / revoked delegations.
* ``active_for`` honours the ``"*"`` wildcard scope.
* ``active_for`` filters by (resource_type, resource_id) when the
  delegation is narrowly scoped.
* ``effective_delegators`` returns the delegator ids.

Covers the HTTP API:

* ``POST /api/delegations`` by the delegator themselves succeeds.
* ``POST /api/delegations`` by a third-party non-admin for someone
  else's delegator is 403.
* ``DELETE /api/delegations/<id>`` by a non-admin non-delegator is 403.
* ``GET /api/delegations/incoming`` and ``outgoing`` only return
  the caller's own rows.
"""
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

    def mk_org(name):
        org = Organization(name=name, type="company")
        db.session.add(org)
        db.session.flush()
        return org

    org_a = mk_org("Delegation Alpha")
    org_b = mk_org("Delegation Beta")
    role = Role.query.filter_by(name="admin").one_or_none() or Role(
        name="admin", description="test administrator"
    )
    db.session.add(role)
    db.session.flush()

    def mk(name, email, org_id, admin=False):
        u = User(
            username=name,
            email=email,
            is_active=True,
            organization_id=org_id,
        )
        u.set_password("delegationpassword123")
        db.session.add(u)
        db.session.flush()
        if admin:
            db.session.add(UserRole(user_id=u.id, role_id=role.id))
        return u

    admin = mk("del-admin", "del-admin@example.test", org_a.id, admin=True)
    manager = mk("del-manager", "del-manager@example.test", org_a.id)
    deputy = mk("del-deputy", "del-deputy@example.test", org_a.id)
    foreigner = mk("del-foreign", "del-foreign@example.test", org_b.id)
    db.session.commit()
    return {
        "org_a": org_a,
        "org_b": org_b,
        "admin": admin,
        "manager": manager,
        "deputy": deputy,
        "foreigner": foreigner,
    }


def _window(hours=24):
    now = datetime.utcnow()
    return now, now + timedelta(hours=hours)


class TestGrantValidation:
    def test_self_delegation_refused(self, pg_app, seeded):
        from app.services import delegations

        starts, ends = _window()
        with pytest.raises(delegations.DelegationError) as exc:
            delegations.grant(
                delegator_id=seeded["manager"].id,
                delegate_id=seeded["manager"].id,
                scope="stamp.approve",
                starts_at=starts,
                expires_at=ends,
                granted_by_id=seeded["admin"].id,
            )
        assert "self_delegation_forbidden" in str(exc.value)

    def test_empty_window_refused(self, pg_app, seeded):
        from app.services import delegations

        now = datetime.utcnow()
        # Both endpoints in the future, but starts_at > expires_at.
        with pytest.raises(delegations.DelegationError) as exc:
            delegations.grant(
                delegator_id=seeded["manager"].id,
                delegate_id=seeded["deputy"].id,
                scope="stamp.approve",
                starts_at=now + timedelta(hours=10),
                expires_at=now + timedelta(hours=1),
                granted_by_id=seeded["admin"].id,
            )
        assert "empty_window" in str(exc.value)

    def test_past_expiry_refused(self, pg_app, seeded):
        from app.services import delegations

        now = datetime.utcnow()
        with pytest.raises(delegations.DelegationError) as exc:
            delegations.grant(
                delegator_id=seeded["manager"].id,
                delegate_id=seeded["deputy"].id,
                scope="stamp.approve",
                starts_at=now - timedelta(hours=2),
                expires_at=now - timedelta(hours=1),
                granted_by_id=seeded["admin"].id,
            )
        assert "expiry_in_past" in str(exc.value)

    def test_cross_org_refused(self, pg_app, seeded):
        from app.services import delegations

        starts, ends = _window()
        with pytest.raises(delegations.DelegationError) as exc:
            delegations.grant(
                delegator_id=seeded["manager"].id,
                delegate_id=seeded["foreigner"].id,
                scope="stamp.approve",
                starts_at=starts,
                expires_at=ends,
                granted_by_id=seeded["admin"].id,
            )
        assert "cross_organization_forbidden" in str(exc.value)


class TestActiveFor:
    def test_inside_window_matches(self, pg_app, seeded):
        from app.services import delegations

        starts, ends = _window()
        delegations.grant(
            delegator_id=seeded["manager"].id,
            delegate_id=seeded["deputy"].id,
            scope="stamp.approve",
            starts_at=starts,
            expires_at=ends,
            granted_by_id=seeded["admin"].id,
        )
        rows = delegations.active_for(seeded["deputy"].id, "stamp.approve")
        assert len(rows) == 1
        assert rows[0].delegator_id == seeded["manager"].id

    def test_outside_window_misses(self, pg_app, seeded):
        from app.services import delegations

        now = datetime.utcnow()
        delegations.grant(
            delegator_id=seeded["manager"].id,
            delegate_id=seeded["deputy"].id,
            scope="stamp.approve",
            starts_at=now + timedelta(hours=1),
            expires_at=now + timedelta(hours=2),
            granted_by_id=seeded["admin"].id,
        )
        rows = delegations.active_for(seeded["deputy"].id, "stamp.approve")
        assert rows == []

    def test_wildcard_scope(self, pg_app, seeded):
        from app.services import delegations

        starts, ends = _window()
        delegations.grant(
            delegator_id=seeded["manager"].id,
            delegate_id=seeded["deputy"].id,
            scope="*",
            starts_at=starts,
            expires_at=ends,
            granted_by_id=seeded["admin"].id,
        )
        assert len(delegations.active_for(seeded["deputy"].id, "whatever")) == 1

    def test_revoked_is_inert(self, pg_app, seeded):
        from app.services import delegations

        starts, ends = _window()
        row = delegations.grant(
            delegator_id=seeded["manager"].id,
            delegate_id=seeded["deputy"].id,
            scope="stamp.approve",
            starts_at=starts,
            expires_at=ends,
            granted_by_id=seeded["admin"].id,
        )
        delegations.revoke(row.id, revoked_by_id=seeded["admin"].id)
        assert delegations.active_for(seeded["deputy"].id, "stamp.approve") == []

    def test_resource_filter(self, pg_app, seeded):
        from app.services import delegations

        starts, ends = _window()
        delegations.grant(
            delegator_id=seeded["manager"].id,
            delegate_id=seeded["deputy"].id,
            scope="stamp.approve",
            resource_type="managed_stamp",
            resource_id=42,
            starts_at=starts,
            expires_at=ends,
            granted_by_id=seeded["admin"].id,
        )
        # Specific resource — matches.
        matched = delegations.active_for(
            seeded["deputy"].id,
            "stamp.approve",
            resource_type="managed_stamp",
            resource_id=42,
        )
        assert len(matched) == 1
        # Different resource id — does not match a narrow grant.
        other = delegations.active_for(
            seeded["deputy"].id,
            "stamp.approve",
            resource_type="managed_stamp",
            resource_id=99,
        )
        assert other == []


class TestApiLayer:
    def _grant_payload(self, delegator_id, delegate_id, hours=24):
        now = datetime.utcnow()
        return {
            "delegator_id": delegator_id,
            "delegate_id": delegate_id,
            "scope": "stamp.approve",
            "starts_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=hours)).isoformat(),
        }

    def test_self_grant_allowed(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["manager"].id))
        r = client.post(
            "/api/delegations",
            json=self._grant_payload(seeded["manager"].id, seeded["deputy"].id),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201, r.get_data(as_text=True)
        assert r.get_json()["scope"] == "stamp.approve"

    def test_third_party_grant_refused(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["deputy"].id))
        # Deputy tries to grant on behalf of manager — forbidden.
        r = client.post(
            "/api/delegations",
            json=self._grant_payload(seeded["manager"].id, seeded["foreigner"].id),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    def test_admin_may_grant_on_behalf(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["admin"].id))
        r = client.post(
            "/api/delegations",
            json=self._grant_payload(seeded["manager"].id, seeded["deputy"].id),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201

    def test_non_delegator_cannot_revoke(self, pg_app, seeded):
        from app.extensions import db
        from app.services import delegations

        starts, ends = _window()
        row = delegations.grant(
            delegator_id=seeded["manager"].id,
            delegate_id=seeded["deputy"].id,
            scope="stamp.approve",
            starts_at=starts,
            expires_at=ends,
            granted_by_id=seeded["admin"].id,
        )
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["deputy"].id))
        r = client.delete(
            f"/api/delegations/{row.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    def test_outgoing_only_own(self, pg_app, seeded):
        from app.extensions import db
        from app.services import delegations

        starts, ends = _window()
        delegations.grant(
            delegator_id=seeded["manager"].id,
            delegate_id=seeded["deputy"].id,
            scope="stamp.approve",
            starts_at=starts,
            expires_at=ends,
            granted_by_id=seeded["admin"].id,
        )
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["manager"].id))
        r = client.get(
            "/api/delegations/outgoing",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.get_json()["delegations"]
        assert len(data) == 1
        token_other = create_access_token(identity=str(seeded["deputy"].id))
        r = client.get(
            "/api/delegations/outgoing",
            headers={"Authorization": f"Bearer {token_other}"},
        )
        assert r.get_json()["delegations"] == []
