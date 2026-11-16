"""Phase P — outbox DLQ + admin dashboard + bulk participants."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token


@pytest.fixture
def admin_seed(pg_app, tmp_path):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.system import Role, UserRole
    from app.models.user import User

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)
    org = Organization(name="Phase P Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    role = Role.query.filter_by(name="admin").one_or_none() or Role(
        name="admin", description="test"
    )
    db.session.add(role)
    db.session.flush()
    admin = User(
        username="p-admin",
        email="p-admin@example.test",
        is_active=True,
        organization_id=org.id,
    )
    admin.set_password("phase-p-password-123")
    db.session.add(admin)
    db.session.flush()
    db.session.add(UserRole(user_id=admin.id, role_id=role.id))
    regular = User(
        username="p-regular",
        email="p-regular@example.test",
        is_active=True,
        organization_id=org.id,
    )
    regular.set_password("phase-p-password-123")
    db.session.add(regular)
    db.session.commit()
    return {"org": org, "admin": admin, "regular": regular}


# ========================================================= P1 outbox DLQ


class TestOutboxDeadLetter:
    def test_lists_dead_events(self, pg_app, admin_seed):
        from app.extensions import db
        from app.models.event_delivery import OutboxEvent

        dead = OutboxEvent(
            event_type="envelope.prepared",
            aggregate_type="envelope",
            aggregate_id=42,
            organization_id=admin_seed["org"].id,
            payload={"envelope_id": 42},
            idempotency_key="dead-1",
            state="dead",
            attempts=5,
            last_error="downstream_timeout",
        )
        db.session.add(dead)
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(admin_seed["admin"].id))
        r = client.get(
            "/api/_internal/outbox/dead",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        ids = [e["id"] for e in r.get_json()["events"]]
        assert dead.id in ids

    def test_replay_resets_state(self, pg_app, admin_seed):
        from app.extensions import db
        from app.models.event_delivery import OutboxEvent

        dead = OutboxEvent(
            event_type="envelope.prepared",
            aggregate_type="envelope",
            aggregate_id=43,
            organization_id=admin_seed["org"].id,
            payload={"envelope_id": 43},
            idempotency_key="dead-replay-1",
            state="dead",
            attempts=5,
            last_error="downstream_timeout",
        )
        db.session.add(dead)
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(admin_seed["admin"].id))
        r = client.post(
            f"/api/_internal/outbox/dead/{dead.id}/replay",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        body = r.get_json()
        assert body["state"] == "pending"
        assert body["attempts"] == 0

    def test_non_admin_denied(self, pg_app, admin_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(admin_seed["regular"].id))
        r = client.get(
            "/api/_internal/outbox/dead",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403


# ========================================================= P2 dashboard


class TestDashboard:
    def test_admin_dashboard_shape(self, pg_app, admin_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(admin_seed["admin"].id))
        r = client.get(
            "/api/_internal/dashboard",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        body = r.get_json()
        assert body["organization_id"] == admin_seed["org"].id
        for section in ("readiness", "slo", "usage", "outbox", "webhooks"):
            assert section in body
        assert isinstance(body["slo"], list)
        assert body["readiness"]["status"] in {"ok", "degraded"}

    def test_dashboard_requires_admin(self, pg_app, admin_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(admin_seed["regular"].id))
        r = client.get(
            "/api/_internal/dashboard",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403


# ========================================================= P3 bulk invitations


@pytest.fixture
def draft_envelope(pg_app, admin_seed):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.signing_envelope import SigningEnvelope
    from app.models.user import User

    org = admin_seed["org"]
    doc = Document(
        title="Bulk invite doc",
        status="draft",
        created_by=admin_seed["admin"].id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()
    body = b"%PDF-1.4\n% bulk\n%%EOF"
    digest = hashlib.sha256(body).hexdigest()
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key=f"{digest}.pdf",
        file_name="bulk.pdf",
        mime_type="application/pdf",
        file_size=len(body),
        sha256=digest,
        scanner="noop",
        created_by_id=admin_seed["admin"].id,
    )
    db.session.add(blob)
    db.session.flush()
    envelope = SigningEnvelope(
        organization_id=org.id,
        document_id=doc.id,
        document_blob_id=blob.id,
        document_sha256=digest,
        created_by_id=admin_seed["admin"].id,
        state="draft",
    )
    db.session.add(envelope)
    db.session.flush()

    recipients = []
    for n in range(3):
        u = User(
            username=f"bulk-recipient-{n}",
            email=f"bulk-recipient-{n}@example.test",
            is_active=True,
            organization_id=org.id,
        )
        u.set_password("phase-p-password-123")
        db.session.add(u)
        db.session.flush()
        recipients.append(u)
    db.session.commit()
    return {"envelope": envelope, "recipients": recipients}


class TestBulkParticipants:
    def test_all_rows_succeed(self, pg_app, admin_seed, draft_envelope):
        from app.extensions import db
        from app.models.signing_envelope import EnvelopeParticipant

        rows = [
            {"user_id": r.id, "signing_order": i + 1, "role": "signer"}
            for i, r in enumerate(draft_envelope["recipients"])
        ]
        client = pg_app.test_client()
        token = create_access_token(identity=str(admin_seed["admin"].id))
        r = client.post(
            f"/api/envelopes/{draft_envelope['envelope'].id}/participants/bulk",
            json={"participants": rows},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201, r.get_data(as_text=True)
        body = r.get_json()
        assert body["added"] == 3
        assert body["failed"] == 0
        db.session.expire_all()
        count = EnvelopeParticipant.query.filter_by(
            envelope_id=draft_envelope["envelope"].id
        ).count()
        assert count == 3

    def test_mixed_batch_207(self, pg_app, admin_seed, draft_envelope):
        """Duplicate signing order fails one row but siblings succeed."""
        from app.extensions import db
        from app.models.signing_envelope import EnvelopeParticipant

        rows = [
            {
                "user_id": draft_envelope["recipients"][0].id,
                "signing_order": 1,
                "role": "signer",
            },
            {
                "user_id": draft_envelope["recipients"][1].id,
                "signing_order": 1,  # duplicate order
                "role": "signer",
            },
            {
                "user_id": draft_envelope["recipients"][2].id,
                "signing_order": 2,
                "role": "signer",
            },
        ]
        client = pg_app.test_client()
        token = create_access_token(identity=str(admin_seed["admin"].id))
        r = client.post(
            f"/api/envelopes/{draft_envelope['envelope'].id}/participants/bulk",
            json={"participants": rows},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 207
        body = r.get_json()
        assert body["added"] == 2
        assert body["failed"] == 1
        statuses = {r["status"] for r in body["results"]}
        assert statuses == {"succeeded", "failed"}

    def test_all_failures_rolled_back(self, pg_app, admin_seed, draft_envelope):
        from app.extensions import db
        from app.models.signing_envelope import EnvelopeParticipant

        rows = [{"user_id": 99999999, "signing_order": 1, "role": "signer"}]
        client = pg_app.test_client()
        token = create_access_token(identity=str(admin_seed["admin"].id))
        r = client.post(
            f"/api/envelopes/{draft_envelope['envelope'].id}/participants/bulk",
            json={"participants": rows},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400
        db.session.expire_all()
        count = EnvelopeParticipant.query.filter_by(
            envelope_id=draft_envelope["envelope"].id
        ).count()
        assert count == 0

    def test_limit_100(self, pg_app, admin_seed, draft_envelope):
        rows = [
            {
                "user_id": draft_envelope["recipients"][0].id,
                "signing_order": i + 1,
                "role": "signer",
            }
            for i in range(101)
        ]
        client = pg_app.test_client()
        token = create_access_token(identity=str(admin_seed["admin"].id))
        r = client.post(
            f"/api/envelopes/{draft_envelope['envelope'].id}/participants/bulk",
            json={"participants": rows},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 413

    def test_non_draft_envelope_refused(
        self, pg_app, admin_seed, draft_envelope
    ):
        from app.extensions import db

        draft_envelope["envelope"].state = "prepared"
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(admin_seed["admin"].id))
        r = client.post(
            f"/api/envelopes/{draft_envelope['envelope'].id}/participants/bulk",
            json={
                "participants": [
                    {
                        "user_id": draft_envelope["recipients"][0].id,
                        "signing_order": 1,
                        "role": "signer",
                    }
                ]
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 409
