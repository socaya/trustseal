"""Phase AK — bulk document label tag + remove."""
from __future__ import annotations

import pytest
from flask_jwt_extended import create_access_token


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}


@pytest.fixture
def phase_ak_seed(pg_app):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_label import DocumentLabel
    from app.models.organization import Organization
    from app.models.user import User

    org = Organization(name="AK Tenant", type="company")
    other_org = Organization(name="AK Other", type="company")
    db.session.add_all([org, other_org])
    db.session.flush()
    owner = User(
        username="ak-owner",
        email="ak-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-ak-password-123")
    outsider = User(
        username="ak-outsider",
        email="ak-outsider@example.test",
        is_active=True,
        organization_id=other_org.id,
    )
    outsider.set_password("phase-ak-password-123")
    db.session.add_all([owner, outsider])
    db.session.flush()
    docs = []
    for n in range(3):
        d = Document(
            title=f"AK doc {n}",
            status="draft",
            created_by=owner.id,
            organization_id=org.id,
        )
        db.session.add(d)
        db.session.flush()
        docs.append(d)
    # Pre-tag two of three with "finance" for remove tests.
    for doc in docs[:2]:
        db.session.add(
            DocumentLabel(
                document_id=doc.id,
                organization_id=org.id,
                label="finance",
                created_by_id=owner.id,
            )
        )
    db.session.commit()
    return {"org": org, "owner": owner, "outsider": outsider, "documents": docs}


class TestBulkDocLabelAdd:
    def test_all_tagged(self, pg_app, phase_ak_seed):
        from app.extensions import db
        from app.models.documents.document_label import DocumentLabel

        client = pg_app.test_client()
        ids = [d.id for d in phase_ak_seed["documents"]]
        r = client.post(
            "/api/documents/bulk/label",
            json={"document_ids": ids, "label": "quarterly"},
            headers=_auth(phase_ak_seed["owner"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["succeeded"] == 3
        assert body["added"] == 3
        db.session.expire_all()
        assert DocumentLabel.query.filter_by(label="quarterly").count() == 3

    def test_existing_tag_idempotent(self, pg_app, phase_ak_seed):
        client = pg_app.test_client()
        ids = [d.id for d in phase_ak_seed["documents"]]
        r = client.post(
            "/api/documents/bulk/label",
            json={"document_ids": ids, "label": "finance"},
            headers=_auth(phase_ak_seed["owner"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["added"] == 1
        assert body["succeeded"] == 3
        already = [r for r in body["results"] if r.get("already_tagged")]
        assert len(already) == 2

    def test_mixed_batch_207(self, pg_app, phase_ak_seed):
        client = pg_app.test_client()
        ids = [d.id for d in phase_ak_seed["documents"]] + [9999999]
        r = client.post(
            "/api/documents/bulk/label",
            json={"document_ids": ids, "label": "ops"},
            headers=_auth(phase_ak_seed["owner"]),
        )
        assert r.status_code == 207
        body = r.get_json()
        assert body["succeeded"] == 3
        assert body["failed"] == 1

    def test_bad_label_rejected(self, pg_app, phase_ak_seed):
        client = pg_app.test_client()
        r = client.post(
            "/api/documents/bulk/label",
            json={
                "document_ids": [phase_ak_seed["documents"][0].id],
                "label": "has space",
            },
            headers=_auth(phase_ak_seed["owner"]),
        )
        assert r.status_code == 400

    def test_limit_100(self, pg_app, phase_ak_seed):
        client = pg_app.test_client()
        r = client.post(
            "/api/documents/bulk/label",
            json={"document_ids": list(range(1, 102)), "label": "finance"},
            headers=_auth(phase_ak_seed["owner"]),
        )
        assert r.status_code == 413


class TestBulkDocLabelRemove:
    def test_removes_only_tagged(self, pg_app, phase_ak_seed):
        from app.extensions import db
        from app.models.documents.document_label import DocumentLabel

        client = pg_app.test_client()
        ids = [d.id for d in phase_ak_seed["documents"]]
        r = client.post(
            "/api/documents/bulk/label/remove",
            json={"document_ids": ids, "label": "finance"},
            headers=_auth(phase_ak_seed["owner"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["succeeded"] == 3
        assert body["removed"] == 2
        already = [r for r in body["results"] if r.get("already_removed")]
        assert len(already) == 1
        db.session.expire_all()
        assert DocumentLabel.query.filter_by(label="finance").count() == 0

    def test_all_fail_rolls_back(self, pg_app, phase_ak_seed):
        from app.extensions import db
        from app.models.documents.document_label import DocumentLabel

        client = pg_app.test_client()
        r = client.post(
            "/api/documents/bulk/label/remove",
            json={"document_ids": [9999999], "label": "finance"},
            headers=_auth(phase_ak_seed["owner"]),
        )
        assert r.status_code == 400
        db.session.expire_all()
        assert DocumentLabel.query.filter_by(label="finance").count() == 2

    def test_cross_tenant_rows_skipped(self, pg_app, phase_ak_seed):
        from app.extensions import db
        from app.models.documents.document_label import DocumentLabel

        client = pg_app.test_client()
        r = client.post(
            "/api/documents/bulk/label/remove",
            json={
                "document_ids": [phase_ak_seed["documents"][0].id],
                "label": "finance",
            },
            headers=_auth(phase_ak_seed["outsider"]),
        )
        # The outsider does not own the doc → single-row batch fails → 400.
        assert r.status_code == 400
