"""Phase AG — operator profile update + tenant document labels."""
from __future__ import annotations

import pytest
from flask_jwt_extended import create_access_token


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}


# ============================================================ AG1 profile


@pytest.fixture
def ag1_seed(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.user import User

    org = Organization(name="AG1 Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    user = User(
        username="ag1-user",
        email="ag1-user@example.test",
        is_active=True,
        organization_id=org.id,
        first_name="Original",
        last_name="Name",
        phone="+1-555-0000",
    )
    user.set_password("phase-ag-password-123")
    db.session.add(user)
    db.session.commit()
    return {"org": org, "user": user}


class TestProfileUpdate:
    def test_update_fields(self, pg_app, ag1_seed):
        from app.extensions import db
        from app.models.user import User

        client = pg_app.test_client()
        r = client.patch(
            "/api/auth/me",
            json={"first_name": "New", "phone": "+1-555-9999"},
            headers=_auth(ag1_seed["user"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["first_name"] == "New"
        assert body["phone"] == "+1-555-9999"
        db.session.expire_all()
        refreshed = db.session.get(User, ag1_seed["user"].id)
        assert refreshed.first_name == "New"
        assert refreshed.last_name == "Name"  # unchanged
        assert refreshed.phone == "+1-555-9999"

    def test_null_clears_field(self, pg_app, ag1_seed):
        from app.extensions import db
        from app.models.user import User

        client = pg_app.test_client()
        r = client.patch(
            "/api/auth/me",
            json={"last_name": None},
            headers=_auth(ag1_seed["user"]),
        )
        assert r.status_code == 200
        db.session.expire_all()
        refreshed = db.session.get(User, ag1_seed["user"].id)
        assert refreshed.last_name is None

    def test_unknown_fields_rejected(self, pg_app, ag1_seed):
        client = pg_app.test_client()
        for bad in (
            {"email": "new@example.test"},
            {"password": "something"},
            {"username": "newname"},
        ):
            r = client.patch(
                "/api/auth/me",
                json=bad,
                headers=_auth(ag1_seed["user"]),
            )
            assert r.status_code == 400, bad

    def test_overlong_field_rejected(self, pg_app, ag1_seed):
        client = pg_app.test_client()
        r = client.patch(
            "/api/auth/me",
            json={"first_name": "x" * 81},
            headers=_auth(ag1_seed["user"]),
        )
        assert r.status_code == 400


# ============================================================ AG2 document labels


@pytest.fixture
def ag2_seed(pg_app):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_label import DocumentLabel
    from app.models.organization import Organization
    from app.models.user import User

    org = Organization(name="AG2 Tenant", type="company")
    other_org = Organization(name="AG2 Other", type="company")
    db.session.add_all([org, other_org])
    db.session.flush()
    owner = User(
        username="ag2-owner",
        email="ag2-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-ag-password-123")
    intruder = User(
        username="ag2-intruder",
        email="ag2-intruder@example.test",
        is_active=True,
        organization_id=other_org.id,
    )
    intruder.set_password("phase-ag-password-123")
    db.session.add_all([owner, intruder])
    db.session.flush()
    doc1 = Document(
        title="AG2 doc 1",
        status="draft",
        created_by=owner.id,
        organization_id=org.id,
    )
    doc2 = Document(
        title="AG2 doc 2",
        status="draft",
        created_by=owner.id,
        organization_id=org.id,
    )
    db.session.add_all([doc1, doc2])
    db.session.flush()
    for doc_id, label in (
        (doc1.id, "finance"),
        (doc1.id, "hr"),
        (doc2.id, "finance"),
    ):
        db.session.add(
            DocumentLabel(
                document_id=doc_id,
                organization_id=org.id,
                label=label,
                created_by_id=owner.id,
            )
        )
    db.session.commit()
    return {"org": org, "owner": owner, "intruder": intruder}


class TestTenantDocumentLabelList:
    def test_returns_unique_labels_with_counts(self, pg_app, ag2_seed):
        client = pg_app.test_client()
        r = client.get(
            "/api/documents/labels", headers=_auth(ag2_seed["owner"])
        )
        assert r.status_code == 200
        body = r.get_json()
        label_map = {row["label"]: row["count"] for row in body["labels"]}
        assert label_map == {"finance": 2, "hr": 1}

    def test_scopes_to_tenant(self, pg_app, ag2_seed):
        client = pg_app.test_client()
        r = client.get(
            "/api/documents/labels", headers=_auth(ag2_seed["intruder"])
        )
        assert r.status_code == 200
        assert r.get_json()["labels"] == []
