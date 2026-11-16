"""Phase Q — envelope labels + bulk envelope withdrawal."""
from __future__ import annotations

import hashlib
from datetime import datetime

import pytest
from flask_jwt_extended import create_access_token


@pytest.fixture
def phase_q_seed(pg_app, tmp_path):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.signing_envelope import SigningEnvelope
    from app.models.user import User

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)

    org = Organization(name="Q Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    owner = User(
        username="q-owner",
        email="q-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-q-password-123")
    db.session.add(owner)
    db.session.flush()

    envelopes = []
    for n in range(3):
        doc = Document(
            title=f"Q doc {n}",
            status="draft",
            created_by=owner.id,
            organization_id=org.id,
        )
        db.session.add(doc)
        db.session.flush()
        body = f"%PDF-1.4\n% q{n}\n%%EOF".encode()
        digest = hashlib.sha256(body).hexdigest()
        (private_root / f"{digest}.pdf").write_bytes(body)
        blob = DocumentBlob(
            document_id=doc.id,
            revision=1,
            object_key=f"{digest}.pdf",
            file_name=f"q{n}.pdf",
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
            state="prepared",
            prepared_at=datetime.utcnow(),
        )
        db.session.add(env)
        db.session.flush()
        envelopes.append(env)
    db.session.commit()
    return {"org": org, "owner": owner, "envelopes": envelopes}


# ============================================================= Q1 labels


class TestEnvelopeLabels:
    def test_add_label_round_trip(self, pg_app, phase_q_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(phase_q_seed["owner"].id))
        env = phase_q_seed["envelopes"][0]
        r = client.post(
            f"/api/envelopes/{env.id}/labels",
            json={"label": "Quarterly"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201, r.get_data(as_text=True)
        # Round trip via details shows the label.
        detail = client.get(
            f"/api/envelopes/{env.id}",
            headers={"Authorization": f"Bearer {token}"},
        ).get_json()
        assert detail["labels"] == ["quarterly"]

    def test_add_label_duplicate_idempotent(self, pg_app, phase_q_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(phase_q_seed["owner"].id))
        env = phase_q_seed["envelopes"][0]
        headers = {"Authorization": f"Bearer {token}"}
        a = client.post(
            f"/api/envelopes/{env.id}/labels",
            json={"label": "hr"},
            headers=headers,
        )
        assert a.status_code == 201
        b = client.post(
            f"/api/envelopes/{env.id}/labels",
            json={"label": "HR"},  # normalised
            headers=headers,
        )
        assert b.status_code == 200
        assert b.get_json()["created"] is False

    def test_label_validation(self, pg_app, phase_q_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(phase_q_seed["owner"].id))
        env = phase_q_seed["envelopes"][0]
        headers = {"Authorization": f"Bearer {token}"}
        for bad in ["", "   ", "has space", "weird!", "a" * 61]:
            r = client.post(
                f"/api/envelopes/{env.id}/labels",
                json={"label": bad},
                headers=headers,
            )
            assert r.status_code == 400, bad

    def test_remove_label(self, pg_app, phase_q_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(phase_q_seed["owner"].id))
        env = phase_q_seed["envelopes"][0]
        headers = {"Authorization": f"Bearer {token}"}
        client.post(
            f"/api/envelopes/{env.id}/labels",
            json={"label": "vendor"},
            headers=headers,
        )
        r = client.delete(
            f"/api/envelopes/{env.id}/labels/vendor",
            headers=headers,
        )
        assert r.status_code == 200
        listing = client.get(
            f"/api/envelopes/{env.id}/labels",
            headers=headers,
        ).get_json()
        assert listing["labels"] == []

    def test_list_filter_by_label(self, pg_app, phase_q_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(phase_q_seed["owner"].id))
        headers = {"Authorization": f"Bearer {token}"}
        # Tag two of three envelopes.
        client.post(
            f"/api/envelopes/{phase_q_seed['envelopes'][0].id}/labels",
            json={"label": "finance"},
            headers=headers,
        )
        client.post(
            f"/api/envelopes/{phase_q_seed['envelopes'][2].id}/labels",
            json={"label": "finance"},
            headers=headers,
        )
        r = client.get(
            "/api/envelopes?label=finance", headers=headers
        )
        assert r.status_code == 200
        ids = {row["id"] for row in r.get_json()}
        assert ids == {
            phase_q_seed["envelopes"][0].id,
            phase_q_seed["envelopes"][2].id,
        }


# ============================================================= Q2 bulk withdraw


class TestBulkWithdraw:
    def test_all_rows_withdraw(self, pg_app, phase_q_seed):
        from app.extensions import db
        from app.models.signing_envelope import SigningEnvelope

        client = pg_app.test_client()
        token = create_access_token(identity=str(phase_q_seed["owner"].id))
        ids = [e.id for e in phase_q_seed["envelopes"]]
        r = client.post(
            "/api/envelopes/bulk/withdraw",
            json={"envelope_ids": ids, "reason": "batch cleanup"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["withdrawn"] == 3
        assert body["failed"] == 0
        db.session.expire_all()
        for env_id in ids:
            refreshed = db.session.get(SigningEnvelope, env_id)
            assert refreshed.state == "withdrawn"
            assert refreshed.withdraw_reason == "batch cleanup"

    def test_mixed_batch_207(self, pg_app, phase_q_seed):
        from app.extensions import db
        from app.models.signing_envelope import SigningEnvelope

        # Flip one envelope to draft so it is not eligible.
        phase_q_seed["envelopes"][1].state = "draft"
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(phase_q_seed["owner"].id))
        ids = [e.id for e in phase_q_seed["envelopes"]] + [99999999]
        r = client.post(
            "/api/envelopes/bulk/withdraw",
            json={"envelope_ids": ids},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 207
        body = r.get_json()
        assert body["withdrawn"] == 2
        assert body["failed"] == 2
        failures = [
            r["error_code"] for r in body["results"] if r["status"] == "failed"
        ]
        assert "state_not_prepared" in failures
        assert "envelope_not_found" in failures

    def test_all_fail_rolls_back(self, pg_app, phase_q_seed):
        from app.extensions import db
        from app.models.signing_envelope import SigningEnvelope

        client = pg_app.test_client()
        token = create_access_token(identity=str(phase_q_seed["owner"].id))
        r = client.post(
            "/api/envelopes/bulk/withdraw",
            json={"envelope_ids": [99999999]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400
        # Nothing in the seed changed state.
        db.session.expire_all()
        for env in phase_q_seed["envelopes"]:
            refreshed = db.session.get(SigningEnvelope, env.id)
            assert refreshed.state == "prepared"

    def test_decisions_recorded_blocks_row(self, pg_app, phase_q_seed):
        from app.extensions import db
        from app.models.signer_decision import (
            SignerChallenge,
            SignerDecision,
        )
        from app.models.signing_envelope import EnvelopeParticipant

        owner = phase_q_seed["owner"]
        env = phase_q_seed["envelopes"][0]
        participant = EnvelopeParticipant(
            envelope_id=env.id,
            user_id=owner.id,
            signing_order=1,
            role="signer",
        )
        db.session.add(participant)
        db.session.flush()
        challenge = SignerChallenge(
            envelope_id=env.id,
            participant_id=participant.id,
            user_id=owner.id,
            document_sha256=env.document_sha256,
            nonce_sha256="n" * 64,
            issued_at=datetime.utcnow(),
            expires_at=datetime.utcnow(),
            consumed_at=datetime.utcnow(),
        )
        db.session.add(challenge)
        db.session.flush()
        db.session.add(
            SignerDecision(
                envelope_id=env.id,
                participant_id=participant.id,
                user_id=owner.id,
                challenge_id=challenge.id,
                decision="acknowledged",
                document_sha256=env.document_sha256,
                consent_version="review-intent-v1",
                consent_sha256="d" * 64,
                recorded_at=datetime.utcnow(),
            )
        )
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(owner.id))
        r = client.post(
            "/api/envelopes/bulk/withdraw",
            json={"envelope_ids": [env.id]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400
        body = r.get_json()
        assert body["results"][0]["error_code"] == "decisions_recorded"

    def test_limit_100(self, pg_app, phase_q_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(phase_q_seed["owner"].id))
        r = client.post(
            "/api/envelopes/bulk/withdraw",
            json={"envelope_ids": list(range(1, 102))},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 413
