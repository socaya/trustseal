"""Phase AI — envelope ownership transfer + bulk label removal."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}


# ============================================================ AI1 transfer


@pytest.fixture
def ai1_seed(pg_app, tmp_path):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.signing_envelope import SigningEnvelope
    from app.models.user import User

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)
    org = Organization(name="AI1 Tenant", type="company")
    other_org = Organization(name="AI1 Other", type="company")
    db.session.add_all([org, other_org])
    db.session.flush()
    owner = User(
        username="ai1-owner",
        email="ai1-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-ai-password-123")
    teammate = User(
        username="ai1-teammate",
        email="ai1-teammate@example.test",
        is_active=True,
        organization_id=org.id,
    )
    teammate.set_password("phase-ai-password-123")
    intruder = User(
        username="ai1-intruder",
        email="ai1-intruder@example.test",
        is_active=True,
        organization_id=other_org.id,
    )
    intruder.set_password("phase-ai-password-123")
    db.session.add_all([owner, teammate, intruder])
    db.session.flush()
    doc = Document(
        title="AI1 doc",
        status="draft",
        created_by=owner.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()
    body = b"%PDF-1.4\n% ai1\n%%EOF"
    digest = hashlib.sha256(body).hexdigest()
    (private_root / f"{digest}.pdf").write_bytes(body)
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key=f"{digest}.pdf",
        file_name="ai1.pdf",
        mime_type="application/pdf",
        file_size=len(body),
        sha256=digest,
        scanner="noop",
        created_by_id=owner.id,
    )
    db.session.add(blob)
    db.session.flush()
    envelope = SigningEnvelope(
        organization_id=org.id,
        document_id=doc.id,
        document_blob_id=blob.id,
        document_sha256=digest,
        created_by_id=owner.id,
        state="draft",
    )
    db.session.add(envelope)
    db.session.commit()
    return {
        "org": org,
        "owner": owner,
        "teammate": teammate,
        "intruder": intruder,
        "envelope": envelope,
    }


class TestEnvelopeTransfer:
    def test_owner_transfers_to_teammate(self, pg_app, ai1_seed):
        from app.extensions import db
        from app.models.operator_notification import OperatorNotification
        from app.models.signing_envelope import SigningEnvelope

        client = pg_app.test_client()
        r = client.post(
            f"/api/envelopes/{ai1_seed['envelope'].id}/transfer",
            json={"new_owner_id": ai1_seed["teammate"].id},
            headers=_auth(ai1_seed["owner"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["owner_id"] == ai1_seed["teammate"].id
        assert body["changed"] is True
        db.session.expire_all()
        refreshed = db.session.get(SigningEnvelope, ai1_seed["envelope"].id)
        assert refreshed.created_by_id == ai1_seed["teammate"].id
        # Notification to the new owner.
        notes = OperatorNotification.query.filter_by(
            recipient_user_id=ai1_seed["teammate"].id,
            kind="envelope.ownership.transferred",
        ).all()
        assert len(notes) == 1

    def test_cross_tenant_target_rejected(self, pg_app, ai1_seed):
        client = pg_app.test_client()
        r = client.post(
            f"/api/envelopes/{ai1_seed['envelope'].id}/transfer",
            json={"new_owner_id": ai1_seed["intruder"].id},
            headers=_auth(ai1_seed["owner"]),
        )
        assert r.status_code == 404

    def test_non_owner_rejected(self, pg_app, ai1_seed):
        client = pg_app.test_client()
        r = client.post(
            f"/api/envelopes/{ai1_seed['envelope'].id}/transfer",
            json={"new_owner_id": ai1_seed["owner"].id},
            headers=_auth(ai1_seed["teammate"]),
        )
        assert r.status_code == 403

    def test_terminal_state_rejected(self, pg_app, ai1_seed):
        from app.extensions import db

        ai1_seed["envelope"].state = "withdrawn"
        db.session.commit()
        client = pg_app.test_client()
        r = client.post(
            f"/api/envelopes/{ai1_seed['envelope'].id}/transfer",
            json={"new_owner_id": ai1_seed["teammate"].id},
            headers=_auth(ai1_seed["owner"]),
        )
        assert r.status_code == 409

    def test_same_owner_is_noop(self, pg_app, ai1_seed):
        client = pg_app.test_client()
        r = client.post(
            f"/api/envelopes/{ai1_seed['envelope'].id}/transfer",
            json={"new_owner_id": ai1_seed["owner"].id},
            headers=_auth(ai1_seed["owner"]),
        )
        assert r.status_code == 200
        assert r.get_json()["changed"] is False

    def test_decisions_recorded_rejected(self, pg_app, ai1_seed):
        from app.extensions import db
        from app.models.signer_decision import (
            SignerChallenge,
            SignerDecision,
        )
        from app.models.signing_envelope import EnvelopeParticipant

        ai1_seed["envelope"].state = "prepared"
        db.session.commit()
        p = EnvelopeParticipant(
            envelope_id=ai1_seed["envelope"].id,
            user_id=ai1_seed["teammate"].id,
            signing_order=1,
            role="signer",
        )
        db.session.add(p)
        db.session.flush()
        challenge = SignerChallenge(
            envelope_id=ai1_seed["envelope"].id,
            participant_id=p.id,
            user_id=p.user_id,
            document_sha256=ai1_seed["envelope"].document_sha256,
            nonce_sha256="n" * 64,
            issued_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=5),
            consumed_at=datetime.utcnow(),
        )
        db.session.add(challenge)
        db.session.flush()
        db.session.add(
            SignerDecision(
                envelope_id=ai1_seed["envelope"].id,
                participant_id=p.id,
                user_id=p.user_id,
                challenge_id=challenge.id,
                decision="acknowledged",
                document_sha256=ai1_seed["envelope"].document_sha256,
                consent_version="review-intent-v1",
                consent_sha256="d" * 64,
                recorded_at=datetime.utcnow(),
            )
        )
        db.session.commit()
        client = pg_app.test_client()
        r = client.post(
            f"/api/envelopes/{ai1_seed['envelope'].id}/transfer",
            json={"new_owner_id": ai1_seed["teammate"].id},
            headers=_auth(ai1_seed["owner"]),
        )
        assert r.status_code == 409


# ============================================================ AI2 bulk label remove


@pytest.fixture
def ai2_seed(pg_app, tmp_path):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.signing_envelope import (
        EnvelopeLabel,
        SigningEnvelope,
    )
    from app.models.user import User

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)

    org = Organization(name="AI2 Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    owner = User(
        username="ai2-owner",
        email="ai2-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-ai-password-123")
    db.session.add(owner)
    db.session.flush()
    envelopes = []
    for n in range(3):
        doc = Document(
            title=f"AI2 doc {n}",
            status="draft",
            created_by=owner.id,
            organization_id=org.id,
        )
        db.session.add(doc)
        db.session.flush()
        body = f"%PDF-1.4\n% ai2-{n}\n%%EOF".encode()
        digest = hashlib.sha256(body).hexdigest()
        (private_root / f"{digest}.pdf").write_bytes(body)
        blob = DocumentBlob(
            document_id=doc.id,
            revision=1,
            object_key=f"{digest}.pdf",
            file_name=f"ai2-{n}.pdf",
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
    # Tag two of three with "finance".
    for env in envelopes[:2]:
        db.session.add(
            EnvelopeLabel(
                envelope_id=env.id,
                organization_id=org.id,
                label="finance",
                created_by_id=owner.id,
            )
        )
    db.session.commit()
    return {"org": org, "owner": owner, "envelopes": envelopes}


class TestBulkLabelRemove:
    def test_removes_only_tagged(self, pg_app, ai2_seed):
        from app.extensions import db
        from app.models.signing_envelope import EnvelopeLabel

        client = pg_app.test_client()
        ids = [e.id for e in ai2_seed["envelopes"]]
        r = client.post(
            "/api/envelopes/bulk/label/remove",
            json={"envelope_ids": ids, "label": "finance"},
            headers=_auth(ai2_seed["owner"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["succeeded"] == 3
        assert body["removed"] == 2
        already = [r for r in body["results"] if r.get("already_removed")]
        assert len(already) == 1
        db.session.expire_all()
        assert EnvelopeLabel.query.filter_by(label="finance").count() == 0

    def test_mixed_batch_207(self, pg_app, ai2_seed):
        client = pg_app.test_client()
        ids = [e.id for e in ai2_seed["envelopes"]] + [9999999]
        r = client.post(
            "/api/envelopes/bulk/label/remove",
            json={"envelope_ids": ids, "label": "finance"},
            headers=_auth(ai2_seed["owner"]),
        )
        assert r.status_code == 207
        body = r.get_json()
        assert body["succeeded"] == 3
        assert body["failed"] == 1
        failure = next(
            r for r in body["results"] if r["status"] == "failed"
        )
        assert failure["error_code"] == "envelope_not_found"

    def test_all_fail_rolls_back(self, pg_app, ai2_seed):
        from app.extensions import db
        from app.models.signing_envelope import EnvelopeLabel

        client = pg_app.test_client()
        r = client.post(
            "/api/envelopes/bulk/label/remove",
            json={"envelope_ids": [9999999], "label": "finance"},
            headers=_auth(ai2_seed["owner"]),
        )
        assert r.status_code == 400
        db.session.expire_all()
        # Pre-existing labels unchanged.
        assert EnvelopeLabel.query.filter_by(label="finance").count() == 2

    def test_limit_100(self, pg_app, ai2_seed):
        client = pg_app.test_client()
        r = client.post(
            "/api/envelopes/bulk/label/remove",
            json={"envelope_ids": list(range(1, 102)), "label": "finance"},
            headers=_auth(ai2_seed["owner"]),
        )
        assert r.status_code == 413
