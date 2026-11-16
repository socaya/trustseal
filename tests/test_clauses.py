"""Clause library (E2)."""
from __future__ import annotations

import pytest
from flask_jwt_extended import create_access_token


@pytest.fixture
def seeded(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.user import User

    def mk_org(name):
        o = Organization(name=name, type="company")
        db.session.add(o)
        db.session.flush()
        return o

    org_a = mk_org("Clause Tenant A")
    org_b = mk_org("Clause Tenant B")

    def mk_user(name, email, org):
        u = User(
            username=name,
            email=email,
            is_active=True,
            organization_id=org.id,
        )
        u.set_password("clausepassword12345")
        db.session.add(u)
        db.session.flush()
        return u

    author = mk_user("clause-author", "clause-author@example.test", org_a)
    reviewer = mk_user(
        "clause-reviewer", "clause-reviewer@example.test", org_a
    )
    foreign = mk_user(
        "clause-foreign", "clause-foreign@example.test", org_b
    )
    db.session.commit()
    return {
        "org_a": org_a,
        "author": author,
        "reviewer": reviewer,
        "foreign": foreign,
    }


class TestService:
    def test_create_starts_in_draft(self, pg_app, seeded):
        from app.services import clauses

        c = clauses.create_clause(
            seeded["org_a"].id,
            "Confidentiality",
            "The parties agree to keep information confidential.",
            created_by_id=seeded["author"].id,
        )
        assert c.state == "draft"
        assert c.versions[0].revision == 1

    def test_duplicate_name_refused(self, pg_app, seeded):
        from app.extensions import db
        from app.services import clauses

        clauses.create_clause(
            seeded["org_a"].id,
            "NDA Clause",
            "text",
            created_by_id=seeded["author"].id,
        )
        db.session.commit()
        with pytest.raises(Exception):
            clauses.create_clause(
                seeded["org_a"].id,
                "NDA Clause",
                "other",
                created_by_id=seeded["author"].id,
            )
            db.session.commit()

    def test_new_version_refused_on_approved(self, pg_app, seeded):
        from app.extensions import db
        from app.services import clauses

        c = clauses.create_clause(
            seeded["org_a"].id,
            "Non-Compete",
            "v1 body",
            created_by_id=seeded["author"].id,
        )
        clauses.approve(c, approved_by_id=seeded["reviewer"].id)
        db.session.commit()
        with pytest.raises(clauses.ClauseError) as exc:
            clauses.new_version(c, "v2 body", author_id=seeded["author"].id)
        assert "reopen" in str(exc.value)

    def test_reopen_back_to_draft(self, pg_app, seeded):
        from app.extensions import db
        from app.services import clauses

        c = clauses.create_clause(
            seeded["org_a"].id,
            "Termination",
            "v1",
            created_by_id=seeded["author"].id,
        )
        clauses.approve(c, approved_by_id=seeded["reviewer"].id)
        clauses.reopen(c, author_id=seeded["author"].id)
        assert c.state == "draft"


class TestApi:
    def _create(self, pg_app, user, name="SampleClause", body="body"):
        token = create_access_token(identity=str(user.id))
        client = pg_app.test_client()
        r = client.post(
            "/api/clauses",
            json={"name": name, "body": body},
            headers={"Authorization": f"Bearer {token}"},
        )
        return r, token

    def test_full_lifecycle(self, pg_app, seeded):
        r, _ = self._create(pg_app, seeded["author"])
        assert r.status_code == 201
        clause_id = r.get_json()["id"]
        client = pg_app.test_client()
        reviewer_token = create_access_token(
            identity=str(seeded["reviewer"].id)
        )
        r = client.post(
            f"/api/clauses/{clause_id}/approve",
            headers={"Authorization": f"Bearer {reviewer_token}"},
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        assert r.get_json()["state"] == "approved"

    def test_self_approve_refused(self, pg_app, seeded):
        r, token = self._create(pg_app, seeded["author"])
        clause_id = r.get_json()["id"]
        client = pg_app.test_client()
        r = client.post(
            f"/api/clauses/{clause_id}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    def test_cross_tenant_is_404(self, pg_app, seeded):
        r, _ = self._create(pg_app, seeded["author"])
        clause_id = r.get_json()["id"]
        client = pg_app.test_client()
        foreign_token = create_access_token(
            identity=str(seeded["foreign"].id)
        )
        r = client.get(
            f"/api/clauses/{clause_id}",
            headers={"Authorization": f"Bearer {foreign_token}"},
        )
        assert r.status_code == 404

    def test_list_filter_by_state(self, pg_app, seeded):
        from app.extensions import db
        from app.services import clauses

        a = clauses.create_clause(
            seeded["org_a"].id,
            "A",
            "a",
            created_by_id=seeded["author"].id,
        )
        b = clauses.create_clause(
            seeded["org_a"].id,
            "B",
            "b",
            created_by_id=seeded["author"].id,
        )
        clauses.approve(b, approved_by_id=seeded["reviewer"].id)
        db.session.commit()
        token = create_access_token(identity=str(seeded["author"].id))
        client = pg_app.test_client()
        r = client.get(
            "/api/clauses?state=approved",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        ids = [c["id"] for c in r.get_json()["clauses"]]
        assert ids == [b.id]
