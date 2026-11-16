"""Phase AE — bulk document delete + envelope review receipt listing."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}


# ============================================================ AE1 bulk delete


@pytest.fixture
def ae1_seed(pg_app):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.organization import Organization
    from app.models.user import User

    org = Organization(name="AE1 Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    owner = User(
        username="ae1-owner",
        email="ae1-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-ae-password-123")
    db.session.add(owner)
    db.session.flush()
    drafts = []
    for n in range(3):
        d = Document(
            title=f"AE1 draft {n}",
            status="draft",
            created_by=owner.id,
            organization_id=org.id,
        )
        db.session.add(d)
        db.session.flush()
        drafts.append(d)
    final = Document(
        title="AE1 final",
        status="signed",
        created_by=owner.id,
        organization_id=org.id,
    )
    db.session.add(final)
    db.session.commit()
    return {"org": org, "owner": owner, "drafts": drafts, "final": final}


class TestBulkDocumentDelete:
    def test_all_drafts_deleted(self, pg_app, ae1_seed):
        from app.extensions import db
        from app.models.documents.document import Document

        client = pg_app.test_client()
        ids = [d.id for d in ae1_seed["drafts"]]
        r = client.post(
            "/api/documents/bulk/delete",
            json={"document_ids": ids},
            headers=_auth(ae1_seed["owner"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["succeeded"] == 3
        assert body["deleted"] == 3
        db.session.expire_all()
        for doc_id in ids:
            doc = db.session.get(Document, doc_id)
            assert doc.deleted_at is not None

    def test_mixed_batch_207(self, pg_app, ae1_seed):
        client = pg_app.test_client()
        ids = [d.id for d in ae1_seed["drafts"]] + [
            ae1_seed["final"].id,
            9999999,
        ]
        r = client.post(
            "/api/documents/bulk/delete",
            json={"document_ids": ids},
            headers=_auth(ae1_seed["owner"]),
        )
        assert r.status_code == 207
        body = r.get_json()
        assert body["succeeded"] == 3
        assert body["failed"] == 2
        failures = {r["error_code"] for r in body["results"] if r["status"] == "failed"}
        assert failures == {"state_not_draft", "document_not_found"}

    def test_already_deleted_idempotent(self, pg_app, ae1_seed):
        from app.extensions import db

        ae1_seed["drafts"][0].deleted_at = datetime.utcnow()
        db.session.commit()
        client = pg_app.test_client()
        r = client.post(
            "/api/documents/bulk/delete",
            json={
                "document_ids": [
                    ae1_seed["drafts"][0].id,
                    ae1_seed["drafts"][1].id,
                ]
            },
            headers=_auth(ae1_seed["owner"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["succeeded"] == 2
        assert body["deleted"] == 1
        already = [r for r in body["results"] if r.get("already_deleted")]
        assert len(already) == 1

    def test_all_fail_rolls_back(self, pg_app, ae1_seed):
        from app.extensions import db
        from app.models.documents.document import Document

        client = pg_app.test_client()
        r = client.post(
            "/api/documents/bulk/delete",
            json={"document_ids": [9999999]},
            headers=_auth(ae1_seed["owner"]),
        )
        assert r.status_code == 400
        db.session.expire_all()
        for draft in ae1_seed["drafts"]:
            refreshed = db.session.get(Document, draft.id)
            assert refreshed.deleted_at is None

    def test_limit_100(self, pg_app, ae1_seed):
        client = pg_app.test_client()
        r = client.post(
            "/api/documents/bulk/delete",
            json={"document_ids": list(range(1, 102))},
            headers=_auth(ae1_seed["owner"]),
        )
        assert r.status_code == 413


# ============================================================ AE2 receipt listing


@pytest.fixture
def ae2_seed(pg_app, tmp_path):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.review_receipt import ReviewReceipt
    from app.models.signer_decision import SignerChallenge, SignerDecision
    from app.models.signing_envelope import (
        EnvelopeParticipant,
        SigningEnvelope,
    )
    from app.models.user import User

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)

    org = Organization(name="AE2 Tenant", type="company")
    other_org = Organization(name="AE2 Other", type="company")
    db.session.add_all([org, other_org])
    db.session.flush()
    owner = User(
        username="ae2-owner",
        email="ae2-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-ae-password-123")
    signer = User(
        username="ae2-signer",
        email="ae2-signer@example.test",
        is_active=True,
        organization_id=org.id,
    )
    signer.set_password("phase-ae-password-123")
    intruder = User(
        username="ae2-intruder",
        email="ae2-intruder@example.test",
        is_active=True,
        organization_id=other_org.id,
    )
    intruder.set_password("phase-ae-password-123")
    db.session.add_all([owner, signer, intruder])
    db.session.flush()
    doc = Document(
        title="AE2 doc",
        status="draft",
        created_by=owner.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()
    body = b"%PDF-1.4\n% ae2\n%%EOF"
    digest = hashlib.sha256(body).hexdigest()
    (private_root / f"{digest}.pdf").write_bytes(body)
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key=f"{digest}.pdf",
        file_name="ae2.pdf",
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
        state="prepared",
        prepared_at=datetime.utcnow(),
    )
    db.session.add(envelope)
    db.session.flush()
    participant = EnvelopeParticipant(
        envelope_id=envelope.id,
        user_id=signer.id,
        signing_order=1,
        role="signer",
    )
    db.session.add(participant)
    db.session.flush()
    challenge = SignerChallenge(
        envelope_id=envelope.id,
        participant_id=participant.id,
        user_id=signer.id,
        document_sha256=digest,
        nonce_sha256="n" * 64,
        issued_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=5),
        consumed_at=datetime.utcnow(),
    )
    db.session.add(challenge)
    db.session.flush()
    decision = SignerDecision(
        envelope_id=envelope.id,
        participant_id=participant.id,
        user_id=signer.id,
        challenge_id=challenge.id,
        decision="acknowledged",
        document_sha256=digest,
        consent_version="review-intent-v1",
        consent_sha256="d" * 64,
        recorded_at=datetime.utcnow(),
    )
    db.session.add(decision)
    db.session.flush()
    receipt = ReviewReceipt(
        decision_id=decision.id,
        envelope_id=envelope.id,
        organization_id=org.id,
        payload={"decision": "acknowledged", "envelope_id": envelope.id},
        algorithm="ed25519",
        key_id="deadbeef",
        signature="c0ffee" * 10,
    )
    db.session.add(receipt)
    db.session.commit()
    return {
        "org": org,
        "owner": owner,
        "intruder": intruder,
        "envelope": envelope,
        "receipt": receipt,
    }


class TestReceiptListing:
    def test_returns_receipt(self, pg_app, ae2_seed):
        client = pg_app.test_client()
        r = client.get(
            f"/api/envelopes/{ae2_seed['envelope'].id}/receipts",
            headers=_auth(ae2_seed["owner"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["envelope_id"] == ae2_seed["envelope"].id
        assert len(body["receipts"]) == 1
        row = body["receipts"][0]
        assert row["algorithm"] == "ed25519"
        assert row["key_id"] == "deadbeef"
        # Payload must round-trip verbatim.
        assert row["payload"]["decision"] == "acknowledged"
        assert row["signature"] == ae2_seed["receipt"].signature

    def test_cross_tenant_404(self, pg_app, ae2_seed):
        client = pg_app.test_client()
        r = client.get(
            f"/api/envelopes/{ae2_seed['envelope'].id}/receipts",
            headers=_auth(ae2_seed["intruder"]),
        )
        assert r.status_code == 404

    def test_empty_when_no_receipts(self, pg_app, ae2_seed):
        from app.extensions import db
        from app.models.review_receipt import ReviewReceipt

        db.session.delete(ae2_seed["receipt"])
        db.session.commit()
        client = pg_app.test_client()
        r = client.get(
            f"/api/envelopes/{ae2_seed['envelope'].id}/receipts",
            headers=_auth(ae2_seed["owner"]),
        )
        assert r.status_code == 200
        assert r.get_json()["receipts"] == []
