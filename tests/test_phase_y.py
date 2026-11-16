"""Phase Y — document labels + bulk envelope archival."""
from __future__ import annotations

import hashlib
from datetime import datetime

import pytest
from flask_jwt_extended import create_access_token


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}


@pytest.fixture
def phase_y_seed(pg_app, tmp_path):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.signing_envelope import SigningEnvelope
    from app.models.user import User

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)

    org = Organization(name="Y Tenant", type="company")
    other_org = Organization(name="Y Other", type="company")
    db.session.add_all([org, other_org])
    db.session.flush()
    owner = User(
        username="y-owner",
        email="y-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-y-password-123")
    other_owner = User(
        username="y-other-owner",
        email="y-other-owner@example.test",
        is_active=True,
        organization_id=other_org.id,
    )
    other_owner.set_password("phase-y-password-123")
    db.session.add_all([owner, other_owner])
    db.session.flush()

    documents = []
    envelopes_terminal = []
    envelopes_active = []
    for n in range(3):
        doc = Document(
            title=f"Y doc {n}",
            status="draft",
            created_by=owner.id,
            organization_id=org.id,
        )
        db.session.add(doc)
        db.session.flush()
        documents.append(doc)
        body = f"%PDF-1.4\n% y-{n}\n%%EOF".encode()
        digest = hashlib.sha256(body).hexdigest()
        (private_root / f"{digest}.pdf").write_bytes(body)
        blob = DocumentBlob(
            document_id=doc.id,
            revision=1,
            object_key=f"{digest}.pdf",
            file_name=f"y-{n}.pdf",
            mime_type="application/pdf",
            file_size=len(body),
            sha256=digest,
            scanner="noop",
            created_by_id=owner.id,
        )
        db.session.add(blob)
        db.session.flush()
        # Two terminal envelopes + one active.
        env = SigningEnvelope(
            organization_id=org.id,
            document_id=doc.id,
            document_blob_id=blob.id,
            document_sha256=digest,
            created_by_id=owner.id,
            state="withdrawn" if n < 2 else "prepared",
            prepared_at=datetime.utcnow(),
            withdrawn_at=datetime.utcnow() if n < 2 else None,
        )
        db.session.add(env)
        db.session.flush()
        if n < 2:
            envelopes_terminal.append(env)
        else:
            envelopes_active.append(env)
    db.session.commit()
    return {
        "org": org,
        "other_org": other_org,
        "owner": owner,
        "other_owner": other_owner,
        "documents": documents,
        "envelopes_terminal": envelopes_terminal,
        "envelopes_active": envelopes_active,
    }


# ============================================================ Y1 labels


class TestDocumentLabels:
    def test_add_and_list(self, pg_app, phase_y_seed):
        client = pg_app.test_client()
        doc = phase_y_seed["documents"][0]
        headers = _auth(phase_y_seed["owner"])
        r = client.post(
            f"/api/documents/{doc.id}/labels",
            json={"label": "Finance"},
            headers=headers,
        )
        assert r.status_code == 201
        listing = client.get(
            f"/api/documents/{doc.id}/labels", headers=headers
        ).get_json()
        assert listing["labels"] == ["finance"]

    def test_duplicate_idempotent(self, pg_app, phase_y_seed):
        client = pg_app.test_client()
        doc = phase_y_seed["documents"][0]
        headers = _auth(phase_y_seed["owner"])
        first = client.post(
            f"/api/documents/{doc.id}/labels",
            json={"label": "hr"},
            headers=headers,
        )
        assert first.status_code == 201
        second = client.post(
            f"/api/documents/{doc.id}/labels",
            json={"label": "HR"},
            headers=headers,
        )
        assert second.status_code == 200
        assert second.get_json()["created"] is False

    def test_remove_label(self, pg_app, phase_y_seed):
        client = pg_app.test_client()
        doc = phase_y_seed["documents"][0]
        headers = _auth(phase_y_seed["owner"])
        client.post(
            f"/api/documents/{doc.id}/labels",
            json={"label": "vendor"},
            headers=headers,
        )
        r = client.delete(
            f"/api/documents/{doc.id}/labels/vendor", headers=headers
        )
        assert r.status_code == 200

    def test_list_documents_by_label(self, pg_app, phase_y_seed):
        client = pg_app.test_client()
        headers = _auth(phase_y_seed["owner"])
        client.post(
            f"/api/documents/{phase_y_seed['documents'][0].id}/labels",
            json={"label": "ops"},
            headers=headers,
        )
        client.post(
            f"/api/documents/{phase_y_seed['documents'][2].id}/labels",
            json={"label": "ops"},
            headers=headers,
        )
        r = client.get("/api/documents/by-label/ops", headers=headers)
        assert r.status_code == 200
        body = r.get_json()
        ids = {row["id"] for row in body["documents"]}
        assert ids == {
            phase_y_seed["documents"][0].id,
            phase_y_seed["documents"][2].id,
        }

    def test_label_validation(self, pg_app, phase_y_seed):
        client = pg_app.test_client()
        doc = phase_y_seed["documents"][0]
        headers = _auth(phase_y_seed["owner"])
        for bad in ["", "has space", "!bang", "a" * 61]:
            r = client.post(
                f"/api/documents/{doc.id}/labels",
                json={"label": bad},
                headers=headers,
            )
            assert r.status_code == 400, bad

    def test_cross_tenant_document_hidden(self, pg_app, phase_y_seed):
        client = pg_app.test_client()
        doc = phase_y_seed["documents"][0]
        headers = _auth(phase_y_seed["other_owner"])
        r = client.post(
            f"/api/documents/{doc.id}/labels",
            json={"label": "hr"},
            headers=headers,
        )
        assert r.status_code == 404


# ============================================================ Y2 bulk archive


class TestBulkArchive:
    def test_all_terminal_archive(self, pg_app, phase_y_seed):
        from app.extensions import db
        from app.models.signing_envelope import SigningEnvelope

        client = pg_app.test_client()
        ids = [e.id for e in phase_y_seed["envelopes_terminal"]]
        r = client.post(
            "/api/envelopes/bulk/archive",
            json={"envelope_ids": ids},
            headers=_auth(phase_y_seed["owner"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["succeeded"] == 2
        assert body["archived"] == 2
        db.session.expire_all()
        for env_id in ids:
            refreshed = db.session.get(SigningEnvelope, env_id)
            assert refreshed.archived_at is not None

    def test_mixed_batch_207(self, pg_app, phase_y_seed):
        client = pg_app.test_client()
        ids = [e.id for e in phase_y_seed["envelopes_terminal"]] + [
            phase_y_seed["envelopes_active"][0].id,
            99999999,
        ]
        r = client.post(
            "/api/envelopes/bulk/archive",
            json={"envelope_ids": ids},
            headers=_auth(phase_y_seed["owner"]),
        )
        assert r.status_code == 207
        body = r.get_json()
        assert body["succeeded"] == 2
        assert body["failed"] == 2
        failures = {r["error_code"] for r in body["results"] if r["status"] == "failed"}
        assert failures == {"state_not_archivable", "envelope_not_found"}

    def test_already_archived_idempotent(self, pg_app, phase_y_seed):
        from app.extensions import db

        client = pg_app.test_client()
        phase_y_seed["envelopes_terminal"][0].archived_at = datetime.utcnow()
        db.session.commit()
        r = client.post(
            "/api/envelopes/bulk/archive",
            json={
                "envelope_ids": [
                    phase_y_seed["envelopes_terminal"][0].id,
                    phase_y_seed["envelopes_terminal"][1].id,
                ]
            },
            headers=_auth(phase_y_seed["owner"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["succeeded"] == 2
        assert body["archived"] == 1
        already = [r for r in body["results"] if r.get("already_archived")]
        assert len(already) == 1

    def test_all_fail_rolls_back(self, pg_app, phase_y_seed):
        from app.extensions import db
        from app.models.signing_envelope import SigningEnvelope

        client = pg_app.test_client()
        r = client.post(
            "/api/envelopes/bulk/archive",
            json={"envelope_ids": [99999999]},
            headers=_auth(phase_y_seed["owner"]),
        )
        assert r.status_code == 400
        db.session.expire_all()
        for env in phase_y_seed["envelopes_terminal"]:
            refreshed = db.session.get(SigningEnvelope, env.id)
            assert refreshed.archived_at is None

    def test_limit_100(self, pg_app, phase_y_seed):
        client = pg_app.test_client()
        r = client.post(
            "/api/envelopes/bulk/archive",
            json={"envelope_ids": list(range(1, 102))},
            headers=_auth(phase_y_seed["owner"]),
        )
        assert r.status_code == 413
