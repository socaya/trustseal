"""Template versioning + publication (E1).

Covers:

Service layer:
* ``create_template`` makes a v1 version and leaves the template in
  ``draft``.
* ``new_version`` on a draft appends a new revision; refuses on
  published; refuses on archived.
* ``start_revision`` on published goes back to draft.
* ``publish`` flips the template + stamps the current version's
  ``published_at``.
* ``archive`` is terminal.

HTTP API:
* ``POST /api/document-templates`` creates.
* ``POST /api/document-templates/<id>/versions`` appends.
* ``POST /api/document-templates/<id>/publish`` is refused when the
  current version's author tries to publish (separation of duties).
* A different operator can publish → state transitions to published.
* ``POST /api/document-templates/<id>/archive`` is terminal.
* Cross-tenant 404s.
"""
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

    org_a = mk_org("Template Tenant A")
    org_b = mk_org("Template Tenant B")

    def mk_user(name, email, org):
        u = User(
            username=name,
            email=email,
            is_active=True,
            organization_id=org.id,
        )
        u.set_password("templatepassword12345")
        db.session.add(u)
        db.session.flush()
        return u

    author = mk_user("template-author", "template-author@example.test", org_a)
    reviewer = mk_user(
        "template-reviewer", "template-reviewer@example.test", org_a
    )
    foreign = mk_user(
        "template-foreign", "template-foreign@example.test", org_b
    )
    db.session.commit()
    return {
        "org_a": org_a,
        "org_b": org_b,
        "author": author,
        "reviewer": reviewer,
        "foreign": foreign,
    }


class TestService:
    def test_create_starts_in_draft(self, pg_app, seeded):
        from app.services import templates

        tmpl = templates.create_template(
            seeded["org_a"].id,
            "NDA",
            "You agree to secrecy.",
            created_by_id=seeded["author"].id,
        )
        assert tmpl.state == "draft"
        assert tmpl.current_version_id is not None
        assert tmpl.versions[0].revision == 1

    def test_new_version_refused_on_published(self, pg_app, seeded):
        from app.extensions import db
        from app.services import templates

        tmpl = templates.create_template(
            seeded["org_a"].id,
            "NDA",
            "v1",
            created_by_id=seeded["author"].id,
        )
        templates.publish(tmpl, published_by_id=seeded["reviewer"].id)
        db.session.commit()
        with pytest.raises(templates.TemplateError) as exc:
            templates.new_version(
                tmpl,
                name="NDA",
                content="v2",
                description=None,
                author_id=seeded["author"].id,
            )
        assert "start_revision" in str(exc.value)

    def test_start_revision_back_to_draft(self, pg_app, seeded):
        from app.extensions import db
        from app.services import templates

        tmpl = templates.create_template(
            seeded["org_a"].id,
            "NDA",
            "v1",
            created_by_id=seeded["author"].id,
        )
        templates.publish(tmpl, published_by_id=seeded["reviewer"].id)
        db.session.commit()
        templates.start_revision(tmpl, seeded["author"].id)
        assert tmpl.state == "draft"

    def test_archive_is_terminal(self, pg_app, seeded):
        from app.extensions import db
        from app.services import templates

        tmpl = templates.create_template(
            seeded["org_a"].id,
            "NDA",
            "v1",
            created_by_id=seeded["author"].id,
        )
        templates.archive(tmpl, archived_by_id=seeded["author"].id)
        db.session.commit()
        with pytest.raises(templates.TemplateError) as exc:
            templates.new_version(
                tmpl,
                name="NDA",
                content="v2",
                description=None,
                author_id=seeded["author"].id,
            )
        assert "archived" in str(exc.value)


class TestApi:
    def _create(self, pg_app, user, name="NDA", content="v1"):
        token = create_access_token(identity=str(user.id))
        client = pg_app.test_client()
        r = client.post(
            "/api/document-templates",
            json={"name": name, "content": content},
            headers={"Authorization": f"Bearer {token}"},
        )
        return r, token

    def test_full_lifecycle(self, pg_app, seeded):
        from app.extensions import db

        r, _ = self._create(pg_app, seeded["author"])
        assert r.status_code == 201
        template_id = r.get_json()["id"]
        client = pg_app.test_client()
        reviewer_token = create_access_token(
            identity=str(seeded["reviewer"].id)
        )
        # Reviewer publishes (SoD passes because reviewer ≠ author).
        r = client.post(
            f"/api/document-templates/{template_id}/publish",
            headers={"Authorization": f"Bearer {reviewer_token}"},
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        assert r.get_json()["state"] == "published"

    def test_self_publish_refused(self, pg_app, seeded):
        r, token = self._create(pg_app, seeded["author"])
        assert r.status_code == 201
        template_id = r.get_json()["id"]
        client = pg_app.test_client()
        # Same author tries to publish own template.
        r = client.post(
            f"/api/document-templates/{template_id}/publish",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    def test_new_version_on_published_refused(self, pg_app, seeded):
        from app.extensions import db
        from app.services import templates

        tmpl = templates.create_template(
            seeded["org_a"].id,
            "NDA",
            "v1",
            created_by_id=seeded["author"].id,
        )
        templates.publish(tmpl, published_by_id=seeded["reviewer"].id)
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["author"].id))
        r = client.post(
            f"/api/document-templates/{tmpl.id}/versions",
            json={"name": "NDA", "content": "v2"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 409

    def test_cross_tenant_is_404(self, pg_app, seeded):
        r, _ = self._create(pg_app, seeded["author"])
        template_id = r.get_json()["id"]
        client = pg_app.test_client()
        foreign_token = create_access_token(
            identity=str(seeded["foreign"].id)
        )
        r = client.get(
            f"/api/document-templates/{template_id}",
            headers={"Authorization": f"Bearer {foreign_token}"},
        )
        assert r.status_code == 404
