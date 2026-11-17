"""Phase AJ — document transfer + bulk envelope transfer."""
from __future__ import annotations

import hashlib
from datetime import datetime

import pytest
from flask_jwt_extended import create_access_token


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}


# ============================================================ AJ1 doc transfer


@pytest.fixture
def aj1_seed(pg_app):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.organization import Organization
    from app.models.user import User

    org = Organization(name="AJ1 Tenant", type="company")
    other_org = Organization(name="AJ1 Other", type="company")
    db.session.add_all([org, other_org])
    db.session.flush()
    owner = User(
        username="aj1-owner",
        email="aj1-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-aj-password-123")
    teammate = User(
        username="aj1-teammate",
        email="aj1-teammate@example.test",
        is_active=True,
        organization_id=org.id,
    )
    teammate.set_password("phase-aj-password-123")
    intruder = User(
        username="aj1-intruder",
        email="aj1-intruder@example.test",
        is_active=True,
        organization_id=other_org.id,
    )
    intruder.set_password("phase-aj-password-123")
    db.session.add_all([owner, teammate, intruder])
    db.session.flush()
    doc = Document(
        title="AJ1 doc",
        status="draft",
        created_by=owner.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.commit()
    return {
        "org": org,
        "owner": owner,
        "teammate": teammate,
        "intruder": intruder,
        "document": doc,
    }


class TestDocumentTransfer:
    def test_owner_transfers_to_teammate(self, pg_app, aj1_seed):
        from app.extensions import db
        from app.models.documents.document import Document
        from app.models.operator_notification import OperatorNotification

        client = pg_app.test_client()
        r = client.post(
            f"/api/documents/{aj1_seed['document'].id}/transfer",
            json={"new_owner_id": aj1_seed["teammate"].id},
            headers=_auth(aj1_seed["owner"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["owner_id"] == aj1_seed["teammate"].id
        db.session.expire_all()
        refreshed = db.session.get(Document, aj1_seed["document"].id)
        assert refreshed.created_by == aj1_seed["teammate"].id
        notes = OperatorNotification.query.filter_by(
            recipient_user_id=aj1_seed["teammate"].id,
            kind="document.ownership.transferred",
        ).all()
        assert len(notes) == 1

    def test_cross_tenant_target_rejected(self, pg_app, aj1_seed):
        client = pg_app.test_client()
        r = client.post(
            f"/api/documents/{aj1_seed['document'].id}/transfer",
            json={"new_owner_id": aj1_seed["intruder"].id},
            headers=_auth(aj1_seed["owner"]),
        )
        assert r.status_code == 404

    def test_non_owner_rejected(self, pg_app, aj1_seed):
        client = pg_app.test_client()
        r = client.post(
            f"/api/documents/{aj1_seed['document'].id}/transfer",
            json={"new_owner_id": aj1_seed["owner"].id},
            headers=_auth(aj1_seed["teammate"]),
        )
        assert r.status_code == 403

    def test_non_transferable_state_rejected(self, pg_app, aj1_seed):
        from app.extensions import db

        aj1_seed["document"].status = "signed"
        db.session.commit()
        client = pg_app.test_client()
        r = client.post(
            f"/api/documents/{aj1_seed['document'].id}/transfer",
            json={"new_owner_id": aj1_seed["teammate"].id},
            headers=_auth(aj1_seed["owner"]),
        )
        assert r.status_code == 409

    def test_same_owner_noop(self, pg_app, aj1_seed):
        client = pg_app.test_client()
        r = client.post(
            f"/api/documents/{aj1_seed['document'].id}/transfer",
            json={"new_owner_id": aj1_seed["owner"].id},
            headers=_auth(aj1_seed["owner"]),
        )
        assert r.status_code == 200
        assert r.get_json()["changed"] is False


# ============================================================ AJ2 bulk envelope transfer


@pytest.fixture
def aj2_seed(pg_app, tmp_path):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.signing_envelope import SigningEnvelope
    from app.models.user import User

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)
    org = Organization(name="AJ2 Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    owner = User(
        username="aj2-owner",
        email="aj2-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-aj-password-123")
    teammate = User(
        username="aj2-teammate",
        email="aj2-teammate@example.test",
        is_active=True,
        organization_id=org.id,
    )
    teammate.set_password("phase-aj-password-123")
    db.session.add_all([owner, teammate])
    db.session.flush()
    envelopes = []
    for n in range(3):
        doc = Document(
            title=f"AJ2 doc {n}",
            status="draft",
            created_by=owner.id,
            organization_id=org.id,
        )
        db.session.add(doc)
        db.session.flush()
        body = f"%PDF-1.4\n% aj2-{n}\n%%EOF".encode()
        digest = hashlib.sha256(body).hexdigest()
        (private_root / f"{digest}.pdf").write_bytes(body)
        blob = DocumentBlob(
            document_id=doc.id,
            revision=1,
            object_key=f"{digest}.pdf",
            file_name=f"aj2-{n}.pdf",
            mime_type="application/pdf",
            file_size=len(body),
            sha256=digest,
            scanner="noop",
            created_by_id=owner.id,
        )
        db.session.add(blob)
        db.session.flush()
        env = SigningEnvelope(
            organization_id=org.id,
            document_id=doc.id,
            document_blob_id=blob.id,
            document_sha256=digest,
            created_by_id=owner.id,
            state="draft",
        )
        db.session.add(env)
        db.session.flush()
        envelopes.append(env)
    db.session.commit()
    return {"org": org, "owner": owner, "teammate": teammate, "envelopes": envelopes}


class TestBulkEnvelopeTransfer:
    def test_all_transferred(self, pg_app, aj2_seed):
        from app.extensions import db
        from app.models.signing_envelope import SigningEnvelope

        client = pg_app.test_client()
        ids = [e.id for e in aj2_seed["envelopes"]]
        r = client.post(
            "/api/envelopes/bulk/transfer",
            json={"envelope_ids": ids, "new_owner_id": aj2_seed["teammate"].id},
            headers=_auth(aj2_seed["owner"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["transferred"] == 3
        db.session.expire_all()
        for env_id in ids:
            refreshed = db.session.get(SigningEnvelope, env_id)
            assert refreshed.created_by_id == aj2_seed["teammate"].id

    def test_mixed_batch_207(self, pg_app, aj2_seed):
        from app.extensions import db

        # Make the second envelope already owned by the target.
        aj2_seed["envelopes"][1].created_by_id = aj2_seed["teammate"].id
        # Make the third envelope terminal.
        aj2_seed["envelopes"][2].state = "withdrawn"
        db.session.commit()
        client = pg_app.test_client()
        ids = [e.id for e in aj2_seed["envelopes"]] + [9999999]
        r = client.post(
            "/api/envelopes/bulk/transfer",
            json={"envelope_ids": ids, "new_owner_id": aj2_seed["teammate"].id},
            headers=_auth(aj2_seed["owner"]),
        )
        assert r.status_code == 207
        body = r.get_json()
        # First + second succeeded (second is already_owner), 2 failed.
        # Actually envelope 2 (idx 1) is owned by teammate, caller is
        # owner (not admin), so caller does not own envelope 2 → fail.
        assert body["failed"] >= 1
        # Envelope 3 (idx 2) is terminal → fail.
        failures = {r["error_code"] for r in body["results"] if r["status"] == "failed"}
        assert "state_not_transferable" in failures
        assert "envelope_not_found" in failures

    def test_cross_tenant_target_rejected(self, pg_app, aj2_seed):
        from app.extensions import db
        from app.models.organization import Organization
        from app.models.user import User

        other_org = Organization(name="AJ2 Other", type="company")
        db.session.add(other_org)
        db.session.flush()
        outsider = User(
            username="aj2-outsider",
            email="aj2-outsider@example.test",
            is_active=True,
            organization_id=other_org.id,
        )
        outsider.set_password("phase-aj-password-123")
        db.session.add(outsider)
        db.session.commit()
        client = pg_app.test_client()
        r = client.post(
            "/api/envelopes/bulk/transfer",
            json={
                "envelope_ids": [aj2_seed["envelopes"][0].id],
                "new_owner_id": outsider.id,
            },
            headers=_auth(aj2_seed["owner"]),
        )
        assert r.status_code == 404

    def test_all_fail_rolls_back(self, pg_app, aj2_seed):
        from app.extensions import db
        from app.models.signing_envelope import SigningEnvelope

        client = pg_app.test_client()
        r = client.post(
            "/api/envelopes/bulk/transfer",
            json={
                "envelope_ids": [9999999],
                "new_owner_id": aj2_seed["teammate"].id,
            },
            headers=_auth(aj2_seed["owner"]),
        )
        assert r.status_code == 400
        db.session.expire_all()
        for env in aj2_seed["envelopes"]:
            refreshed = db.session.get(SigningEnvelope, env.id)
            assert refreshed.created_by_id == aj2_seed["owner"].id

    def test_limit_100(self, pg_app, aj2_seed):
        client = pg_app.test_client()
        r = client.post(
            "/api/envelopes/bulk/transfer",
            json={
                "envelope_ids": list(range(1, 102)),
                "new_owner_id": aj2_seed["teammate"].id,
            },
            headers=_auth(aj2_seed["owner"]),
        )
        assert r.status_code == 413
