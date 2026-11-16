"""Draft autosave with optimistic concurrency (H2).

Covers:

* ``POST /api/document-drafts/<id>/autosave`` with correct
  ``If-Match: <version>`` updates the draft and bumps ``version``.
* Missing ``If-Match`` header → 428.
* Non-integer ``If-Match`` → 400.
* Stale ``If-Match`` → 412 with ``current_version`` payload.
* Unsupported field in body → 400.
* Cross-tenant 404.
"""
from __future__ import annotations

import pytest
from flask_jwt_extended import create_access_token


@pytest.fixture
def seeded(pg_app):
    from app.extensions import db
    from app.models.documents.document_draft import DocumentDraft
    from app.models.organization import Organization
    from app.models.user import User

    def mk_org(name):
        o = Organization(name=name, type="company")
        db.session.add(o)
        db.session.flush()
        return o

    org_a = mk_org("Autosave Tenant A")
    org_b = mk_org("Autosave Tenant B")

    def mk_user(name, email, org):
        u = User(
            username=name,
            email=email,
            is_active=True,
            organization_id=org.id,
        )
        u.set_password("autosavepassword12345")
        db.session.add(u)
        db.session.flush()
        return u

    owner = mk_user("autosave-owner", "autosave-owner@example.test", org_a)
    foreign = mk_user(
        "autosave-foreign", "autosave-foreign@example.test", org_b
    )
    draft = DocumentDraft(
        title="Initial title",
        content="Initial body",
        created_by=owner.id,
        organization_id=org_a.id,
    )
    db.session.add(draft)
    db.session.commit()
    return {
        "org_a": org_a,
        "owner": owner,
        "foreign": foreign,
        "draft": draft,
    }


def _headers(user, if_match=None):
    h = {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}
    if if_match is not None:
        h["If-Match"] = str(if_match)
    return h


class TestAutosave:
    def test_matching_version_bumps(self, pg_app, seeded):
        from app.extensions import db
        from app.models.documents.document_draft import DocumentDraft

        client = pg_app.test_client()
        r = client.post(
            f"/api/document-drafts/{seeded['draft'].id}/autosave",
            json={"title": "Updated", "content": "New body"},
            headers=_headers(seeded["owner"], if_match=1),
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        body = r.get_json()
        assert body["version"] == 2
        db.session.expire_all()
        refreshed = db.session.get(DocumentDraft, seeded["draft"].id)
        assert refreshed.title == "Updated"
        assert refreshed.version == 2

    def test_missing_if_match_428(self, pg_app, seeded):
        client = pg_app.test_client()
        r = client.post(
            f"/api/document-drafts/{seeded['draft'].id}/autosave",
            json={"title": "x"},
            headers=_headers(seeded["owner"]),
        )
        assert r.status_code == 428

    def test_bad_if_match_400(self, pg_app, seeded):
        client = pg_app.test_client()
        r = client.post(
            f"/api/document-drafts/{seeded['draft'].id}/autosave",
            json={"title": "x"},
            headers=_headers(seeded["owner"], if_match="not-a-number"),
        )
        assert r.status_code == 400

    def test_stale_version_412(self, pg_app, seeded):
        client = pg_app.test_client()
        # Bump by one first so current is 2.
        client.post(
            f"/api/document-drafts/{seeded['draft'].id}/autosave",
            json={"title": "A"},
            headers=_headers(seeded["owner"], if_match=1),
        )
        # Second write with the stale version 1.
        r = client.post(
            f"/api/document-drafts/{seeded['draft'].id}/autosave",
            json={"title": "B"},
            headers=_headers(seeded["owner"], if_match=1),
        )
        assert r.status_code == 412
        body = r.get_json()
        assert body["current_version"] == 2
        assert body["expected_version"] == 1

    def test_unsupported_field_400(self, pg_app, seeded):
        client = pg_app.test_client()
        r = client.post(
            f"/api/document-drafts/{seeded['draft'].id}/autosave",
            json={"created_by": 999},
            headers=_headers(seeded["owner"], if_match=1),
        )
        assert r.status_code == 400

    def test_cross_tenant_404(self, pg_app, seeded):
        client = pg_app.test_client()
        r = client.post(
            f"/api/document-drafts/{seeded['draft'].id}/autosave",
            json={"title": "foreign"},
            headers=_headers(seeded["foreign"], if_match=1),
        )
        assert r.status_code == 404
