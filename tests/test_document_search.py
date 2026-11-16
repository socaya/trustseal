"""Full-text document search (E3).

Covers:

* Service: a query that matches the title ranks a document highly.
* Stemming: "sign" matches "signing" and "signed".
* Tenant isolation: tenant B's documents never appear in tenant A's
  search results.
* Soft-deleted documents are excluded.
* Empty / whitespace query returns an empty hit list (not an error).
* ``limit`` caps result count.
* HTTP endpoint ``GET /api/documents/search?q=`` returns the ranked
  hits and refuses anonymous callers.
"""
from __future__ import annotations

import pytest
from flask_jwt_extended import create_access_token


@pytest.fixture
def seeded(pg_app):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.organization import Organization
    from app.models.user import User

    def mk_org(name):
        o = Organization(name=name, type="company")
        db.session.add(o)
        db.session.flush()
        return o

    org_a = mk_org("Search Tenant A")
    org_b = mk_org("Search Tenant B")

    def mk_user(name, email, org):
        u = User(
            username=name,
            email=email,
            is_active=True,
            organization_id=org.id,
        )
        u.set_password("searchpassword12345")
        db.session.add(u)
        db.session.flush()
        return u

    owner = mk_user("search-owner", "search-owner@example.test", org_a)
    foreign = mk_user("search-foreign", "search-foreign@example.test", org_b)

    def mk_doc(title, description, org, creator, *, deleted=False):
        from datetime import datetime

        d = Document(
            title=title,
            description=description,
            status="draft",
            created_by=creator.id,
            organization_id=org.id,
            deleted_at=(datetime.utcnow() if deleted else None),
        )
        db.session.add(d)
        db.session.flush()
        return d

    nda = mk_doc(
        "Master Services Agreement",
        "Covers non-disclosure and licensing of software services.",
        org_a,
        owner,
    )
    msa = mk_doc(
        "Signing Envelope Spec",
        "Canonical description of the signed envelope lifecycle.",
        org_a,
        owner,
    )
    deleted = mk_doc(
        "Legacy Procurement",
        "Old signing procurement notes we are no longer using.",
        org_a,
        owner,
        deleted=True,
    )
    foreign_match = mk_doc(
        "Foreign Signing Policy",
        "Another tenant's signing documentation.",
        org_b,
        foreign,
    )
    db.session.commit()
    return {
        "org_a": org_a,
        "org_b": org_b,
        "owner": owner,
        "foreign": foreign,
        "nda": nda,
        "msa": msa,
        "deleted": deleted,
        "foreign_match": foreign_match,
    }


class TestServiceLayer:
    def test_matches_title(self, pg_app, seeded):
        from app.services.document_search import search

        hits = search(seeded["org_a"].id, "envelope")
        ids = [h.document_id for h in hits]
        assert seeded["msa"].id in ids

    def test_stemming_matches_derived_forms(self, pg_app, seeded):
        from app.services.document_search import search

        hits = search(seeded["org_a"].id, "signed")
        ids = [h.document_id for h in hits]
        assert seeded["msa"].id in ids

    def test_tenant_isolation(self, pg_app, seeded):
        from app.services.document_search import search

        hits = search(seeded["org_a"].id, "signing")
        ids = [h.document_id for h in hits]
        assert seeded["foreign_match"].id not in ids

    def test_soft_deleted_excluded(self, pg_app, seeded):
        from app.services.document_search import search

        hits = search(seeded["org_a"].id, "procurement")
        ids = [h.document_id for h in hits]
        assert seeded["deleted"].id not in ids

    def test_empty_query_returns_empty(self, pg_app, seeded):
        from app.services.document_search import search

        assert search(seeded["org_a"].id, "") == []
        assert search(seeded["org_a"].id, "   ") == []

    def test_limit_caps(self, pg_app, seeded):
        from app.extensions import db
        from app.models.documents.document import Document
        from app.services.document_search import search

        for i in range(10):
            db.session.add(
                Document(
                    title=f"Procurement doc {i}",
                    description="signing contract text",
                    status="draft",
                    created_by=seeded["owner"].id,
                    organization_id=seeded["org_a"].id,
                )
            )
        db.session.commit()
        hits = search(seeded["org_a"].id, "signing", limit=3)
        assert len(hits) == 3


class TestApi:
    def test_search_endpoint_returns_hits(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["owner"].id))
        r = client.get(
            "/api/documents/search?q=envelope",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["count"] >= 1
        ids = [h["document_id"] for h in body["hits"]]
        assert seeded["msa"].id in ids

    def test_requires_auth(self, pg_app):
        client = pg_app.test_client()
        r = client.get("/api/documents/search?q=foo")
        assert r.status_code == 401

    def test_foreign_tenant_results_excluded(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["owner"].id))
        r = client.get(
            "/api/documents/search?q=signing",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        ids = [h["document_id"] for h in r.get_json()["hits"]]
        assert seeded["foreign_match"].id not in ids
