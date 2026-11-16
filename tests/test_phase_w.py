"""Phase W — operator notifications + envelope-expiry auto-publish."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token


@pytest.fixture
def phase_w_seed(pg_app, tmp_path):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.user import User

    org = Organization(name="W Tenant", type="company")
    other_org = Organization(name="W Other", type="company")
    db.session.add_all([org, other_org])
    db.session.flush()
    actor = User(
        username="w-actor",
        email="w-actor@example.test",
        is_active=True,
        organization_id=org.id,
    )
    actor.set_password("phase-w-password-123")
    other_actor = User(
        username="w-other-actor",
        email="w-other-actor@example.test",
        is_active=True,
        organization_id=other_org.id,
    )
    other_actor.set_password("phase-w-password-123")
    db.session.add_all([actor, other_actor])
    db.session.commit()
    return {
        "org": org,
        "other_org": other_org,
        "actor": actor,
        "other_actor": other_actor,
    }


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}


# ============================================================ W1 endpoints


class TestNotificationService:
    def test_publish_and_list(self, pg_app, phase_w_seed):
        from app.extensions import db
        from app.services import operator_notifications

        operator_notifications.publish(
            organization_id=phase_w_seed["org"].id,
            recipient_user_id=phase_w_seed["actor"].id,
            kind="envelope.auto_withdrawn.expired",
            subject_type="signing_envelope",
            subject_id=42,
            summary="Envelope #42 auto-withdrawn",
        )
        db.session.commit()
        client = pg_app.test_client()
        r = client.get("/api/notifications", headers=_auth(phase_w_seed["actor"]))
        assert r.status_code == 200
        body = r.get_json()
        assert len(body["notifications"]) == 1
        assert body["notifications"][0]["kind"] == "envelope.auto_withdrawn.expired"

    def test_count_unread(self, pg_app, phase_w_seed):
        from app.extensions import db
        from app.services import operator_notifications

        for n in range(3):
            operator_notifications.publish(
                organization_id=phase_w_seed["org"].id,
                recipient_user_id=phase_w_seed["actor"].id,
                kind="test.event",
                subject_type="synthetic",
                subject_id=n,
                summary=f"n{n}",
            )
        db.session.commit()
        client = pg_app.test_client()
        r = client.get(
            "/api/notifications/count", headers=_auth(phase_w_seed["actor"])
        )
        assert r.status_code == 200
        assert r.get_json()["unread"] == 3

    def test_mark_read_updates_row(self, pg_app, phase_w_seed):
        from app.extensions import db
        from app.services import operator_notifications

        row = operator_notifications.publish(
            organization_id=phase_w_seed["org"].id,
            recipient_user_id=phase_w_seed["actor"].id,
            kind="test.event",
            subject_type="synthetic",
            subject_id=1,
            summary="n1",
        )
        db.session.commit()
        client = pg_app.test_client()
        r = client.post(
            f"/api/notifications/{row.id}/read",
            headers=_auth(phase_w_seed["actor"]),
        )
        assert r.status_code == 200
        assert r.get_json()["read_at"] is not None
        # Count is now 0.
        count_r = client.get(
            "/api/notifications/count", headers=_auth(phase_w_seed["actor"])
        )
        assert count_r.get_json()["unread"] == 0

    def test_mark_all_read(self, pg_app, phase_w_seed):
        from app.extensions import db
        from app.services import operator_notifications

        for n in range(4):
            operator_notifications.publish(
                organization_id=phase_w_seed["org"].id,
                recipient_user_id=phase_w_seed["actor"].id,
                kind="test.event",
                subject_type="synthetic",
                subject_id=n,
                summary=f"n{n}",
            )
        db.session.commit()
        client = pg_app.test_client()
        r = client.post(
            "/api/notifications/read-all",
            headers=_auth(phase_w_seed["actor"]),
        )
        assert r.status_code == 200
        assert r.get_json()["updated"] == 4

    def test_unread_filter(self, pg_app, phase_w_seed):
        from app.extensions import db
        from app.services import operator_notifications

        a = operator_notifications.publish(
            organization_id=phase_w_seed["org"].id,
            recipient_user_id=phase_w_seed["actor"].id,
            kind="test.event",
            subject_type="synthetic",
            subject_id=1,
            summary="a",
        )
        operator_notifications.publish(
            organization_id=phase_w_seed["org"].id,
            recipient_user_id=phase_w_seed["actor"].id,
            kind="test.event",
            subject_type="synthetic",
            subject_id=2,
            summary="b",
        )
        db.session.commit()
        # Mark one as read via service.
        operator_notifications.mark_read(
            notification_id=a.id,
            recipient_user_id=phase_w_seed["actor"].id,
            organization_id=phase_w_seed["org"].id,
        )
        db.session.commit()
        client = pg_app.test_client()
        r = client.get(
            "/api/notifications?unread=1",
            headers=_auth(phase_w_seed["actor"]),
        )
        assert len(r.get_json()["notifications"]) == 1

    def test_other_tenant_cannot_see_rows(self, pg_app, phase_w_seed):
        from app.extensions import db
        from app.services import operator_notifications

        operator_notifications.publish(
            organization_id=phase_w_seed["org"].id,
            recipient_user_id=phase_w_seed["actor"].id,
            kind="test.event",
            subject_type="synthetic",
            subject_id=1,
            summary="secret",
        )
        db.session.commit()
        client = pg_app.test_client()
        r = client.get(
            "/api/notifications",
            headers=_auth(phase_w_seed["other_actor"]),
        )
        assert r.status_code == 200
        assert r.get_json()["notifications"] == []


# ============================================================ W2 expiry wire


class TestExpiryPublishesNotification:
    def test_auto_withdraw_emits_notification(self, pg_app, tmp_path):
        from app.extensions import db
        from app.models.documents.document import Document
        from app.models.documents.document_blob import DocumentBlob
        from app.models.operator_notification import OperatorNotification
        from app.models.organization import Organization
        from app.models.signing_envelope import SigningEnvelope
        from app.models.user import User
        from app.services import envelope_expiry

        private_root = tmp_path / "private"
        private_root.mkdir(mode=0o700)
        pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)
        org = Organization(name="W Expiry Tenant", type="company")
        db.session.add(org)
        db.session.flush()
        owner = User(
            username="w-exp-owner",
            email="w-exp-owner@example.test",
            is_active=True,
            organization_id=org.id,
        )
        owner.set_password("phase-w-password-123")
        db.session.add(owner)
        db.session.flush()
        doc = Document(
            title="exp doc",
            status="draft",
            created_by=owner.id,
            organization_id=org.id,
        )
        db.session.add(doc)
        db.session.flush()
        body = b"%PDF-1.4\n% w-expiry\n%%EOF"
        digest = hashlib.sha256(body).hexdigest()
        (private_root / f"{digest}.pdf").write_bytes(body)
        blob = DocumentBlob(
            document_id=doc.id,
            revision=1,
            object_key=f"{digest}.pdf",
            file_name="exp.pdf",
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
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        db.session.add(envelope)
        db.session.commit()
        outcomes = envelope_expiry.cancel_expired_envelopes()
        db.session.commit()
        assert len(outcomes) == 1
        rows = OperatorNotification.query.filter_by(
            recipient_user_id=owner.id,
            kind="envelope.auto_withdrawn.expired",
        ).all()
        assert len(rows) == 1
        assert rows[0].subject_id == envelope.id
