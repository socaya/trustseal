"""Teams + team memberships (B2).

Covers the service layer:

* ``create_team`` enforces name length / shape.
* ``add_member`` refuses foreign-organization users.
* Re-adding an active member is idempotent.
* ``remove_member`` soft-deletes; readd works afterwards.
* ``archive_team`` soft-deletes and removes every active membership.
* ``membership_ids`` and ``members`` reflect only active rows.

Covers the HTTP API:

* ``POST /api/teams`` requires admin and returns 201.
* ``POST /api/teams/<id>/members`` adds a member.
* ``DELETE /api/teams/<id>/members/<uid>`` soft-deletes membership.
* ``GET /api/teams/me`` returns the caller's own active team ids
  (works for any authenticated user, not just admin).
* Non-admin cannot create/manage teams (403).
* Cross-organization operations return 404.
"""
from __future__ import annotations

import pytest
from flask_jwt_extended import create_access_token


@pytest.fixture
def seeded(pg_app):
    """Two organizations, each with an admin, a regular user, and a team."""
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.system import Role, UserRole
    from app.models.user import User

    def mk_org(name):
        org = Organization(name=name, type="company")
        db.session.add(org)
        db.session.flush()
        return org

    org_a = mk_org("Teams A")
    org_b = mk_org("Teams B")
    role = Role.query.filter_by(name="admin").one_or_none() or Role(
        name="admin", description="test administrator"
    )
    db.session.add(role)
    db.session.flush()

    def mk_user(username, email, organization_id, admin=False):
        user = User(
            username=username,
            email=email,
            is_active=True,
            organization_id=organization_id,
        )
        user.set_password("teampassword12345")
        db.session.add(user)
        db.session.flush()
        if admin:
            db.session.add(UserRole(user_id=user.id, role_id=role.id))
        return user

    admin_a = mk_user("teams-admin-a", "admin-a@example.test", org_a.id, admin=True)
    user_a = mk_user("teams-user-a", "user-a@example.test", org_a.id)
    extra_a = mk_user("teams-extra-a", "extra-a@example.test", org_a.id)
    admin_b = mk_user("teams-admin-b", "admin-b@example.test", org_b.id, admin=True)
    user_b = mk_user("teams-user-b", "user-b@example.test", org_b.id)
    db.session.commit()
    return {
        "org_a": org_a,
        "org_b": org_b,
        "admin_a": admin_a,
        "user_a": user_a,
        "extra_a": extra_a,
        "admin_b": admin_b,
        "user_b": user_b,
    }


class TestServiceLayer:
    def test_create_team_rejects_empty_name(self, pg_app, seeded):
        from app.services import teams

        with pytest.raises(teams.TeamError):
            teams.create_team(
                seeded["org_a"].id,
                " ",
                created_by_id=seeded["admin_a"].id,
            )

    def test_add_member_rejects_cross_org(self, pg_app, seeded):
        from app.services import teams

        team = teams.create_team(
            seeded["org_a"].id, "Alpha", created_by_id=seeded["admin_a"].id
        )
        with pytest.raises(teams.TeamError) as exc:
            teams.add_member(
                team.id,
                seeded["user_b"].id,
                added_by_id=seeded["admin_a"].id,
            )
        assert "wrong_organization" in str(exc.value)

    def test_add_member_is_idempotent(self, pg_app, seeded):
        from app.extensions import db
        from app.models.team import TeamMembership
        from app.services import teams

        team = teams.create_team(
            seeded["org_a"].id, "Alpha", created_by_id=seeded["admin_a"].id
        )
        a = teams.add_member(team.id, seeded["user_a"].id, added_by_id=seeded["admin_a"].id)
        b = teams.add_member(team.id, seeded["user_a"].id, added_by_id=seeded["admin_a"].id)
        assert a.id == b.id
        assert TeamMembership.query.filter_by(
            team_id=team.id, user_id=seeded["user_a"].id, removed_at=None
        ).count() == 1

    def test_remove_then_readd(self, pg_app, seeded):
        from app.extensions import db
        from app.models.team import TeamMembership
        from app.services import teams

        team = teams.create_team(
            seeded["org_a"].id, "Alpha", created_by_id=seeded["admin_a"].id
        )
        first = teams.add_member(team.id, seeded["user_a"].id, added_by_id=seeded["admin_a"].id)
        teams.remove_member(team.id, seeded["user_a"].id, removed_by_id=seeded["admin_a"].id)
        second = teams.add_member(team.id, seeded["user_a"].id, added_by_id=seeded["admin_a"].id)
        assert first.id != second.id
        removed = TeamMembership.query.filter(
            TeamMembership.team_id == team.id,
            TeamMembership.user_id == seeded["user_a"].id,
            TeamMembership.removed_at.isnot(None),
        ).count()
        assert removed == 1

    def test_archive_cascades_to_memberships(self, pg_app, seeded):
        from app.services import teams

        team = teams.create_team(
            seeded["org_a"].id, "Beta", created_by_id=seeded["admin_a"].id
        )
        teams.add_member(team.id, seeded["user_a"].id, added_by_id=seeded["admin_a"].id)
        teams.add_member(team.id, seeded["extra_a"].id, added_by_id=seeded["admin_a"].id)
        teams.archive_team(team.id, archived_by_id=seeded["admin_a"].id)
        assert teams.members(team.id) == []

    def test_membership_ids_returns_active(self, pg_app, seeded):
        from app.services import teams

        t1 = teams.create_team(seeded["org_a"].id, "One", created_by_id=seeded["admin_a"].id)
        t2 = teams.create_team(seeded["org_a"].id, "Two", created_by_id=seeded["admin_a"].id)
        teams.add_member(t1.id, seeded["user_a"].id, added_by_id=seeded["admin_a"].id)
        teams.add_member(t2.id, seeded["user_a"].id, added_by_id=seeded["admin_a"].id)
        teams.remove_member(t1.id, seeded["user_a"].id, removed_by_id=seeded["admin_a"].id)
        assert teams.membership_ids(seeded["user_a"].id) == [t2.id]


class TestApiLayer:
    def test_create_requires_admin(self, pg_app, seeded):
        client = pg_app.test_client()
        regular = create_access_token(identity=str(seeded["user_a"].id))
        r = client.post(
            "/api/teams",
            json={"name": "Nope"},
            headers={"Authorization": f"Bearer {regular}"},
        )
        assert r.status_code == 403

    def test_admin_creates_team(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["admin_a"].id))
        r = client.post(
            "/api/teams",
            json={"name": "Approvers", "description": "stamp reviewers"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201, r.get_data(as_text=True)
        body = r.get_json()
        assert body["name"] == "Approvers"
        assert body["archived"] is False

    def test_add_and_remove_member(self, pg_app, seeded):
        from app.extensions import db
        from app.services import teams

        team = teams.create_team(
            seeded["org_a"].id, "Reviewers", created_by_id=seeded["admin_a"].id
        )
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["admin_a"].id))
        r = client.post(
            f"/api/teams/{team.id}/members",
            json={"user_id": seeded["user_a"].id, "role_in_team": "lead"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        r = client.delete(
            f"/api/teams/{team.id}/members/{seeded['user_a'].id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200

    def test_cross_org_team_is_404(self, pg_app, seeded):
        from app.extensions import db
        from app.services import teams

        team = teams.create_team(
            seeded["org_b"].id, "Foreign", created_by_id=seeded["admin_b"].id
        )
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["admin_a"].id))
        r = client.post(
            f"/api/teams/{team.id}/members",
            json={"user_id": seeded["user_a"].id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404

    def test_me_endpoint_works_for_regular_user(self, pg_app, seeded):
        from app.extensions import db
        from app.services import teams

        team = teams.create_team(
            seeded["org_a"].id, "Here", created_by_id=seeded["admin_a"].id
        )
        teams.add_member(team.id, seeded["user_a"].id, added_by_id=seeded["admin_a"].id)
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["user_a"].id))
        r = client.get(
            "/api/teams/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.get_json()["team_ids"] == [team.id]
