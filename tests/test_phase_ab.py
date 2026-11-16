"""Phase AB — invitation listing + webhook delivery cancel."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}


# ============================================================ AB1 invitations


@pytest.fixture
def ab1_seed(pg_app, tmp_path):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.signing_envelope import (
        EnvelopeParticipant,
        SigningEnvelope,
    )
    from app.models.user import User
    from app.services import signer_invitations

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)
    org = Organization(name="AB1 Tenant", type="company")
    other_org = Organization(name="AB1 Other", type="company")
    db.session.add_all([org, other_org])
    db.session.flush()
    owner = User(
        username="ab1-owner",
        email="ab1-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-ab-password-123")
    signer = User(
        username="ab1-signer",
        email="ab1-signer@example.test",
        is_active=True,
        organization_id=org.id,
    )
    signer.set_password("phase-ab-password-123")
    intruder = User(
        username="ab1-intruder",
        email="ab1-intruder@example.test",
        is_active=True,
        organization_id=other_org.id,
    )
    intruder.set_password("phase-ab-password-123")
    db.session.add_all([owner, signer, intruder])
    db.session.flush()
    doc = Document(
        title="AB1 doc",
        status="draft",
        created_by=owner.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()
    body = b"%PDF-1.4\n% ab1\n%%EOF"
    digest = hashlib.sha256(body).hexdigest()
    (private_root / f"{digest}.pdf").write_bytes(body)
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key=f"{digest}.pdf",
        file_name="ab1.pdf",
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
    invitation, raw_token = signer_invitations.issue(
        envelope=envelope,
        participant=participant,
        issued_by_id=owner.id,
        lifetime=timedelta(hours=12),
    )
    db.session.commit()
    return {
        "org": org,
        "owner": owner,
        "signer": signer,
        "intruder": intruder,
        "envelope": envelope,
        "participant": participant,
        "invitation": invitation,
        "raw_token": raw_token,
    }


class TestInvitationListing:
    def test_lists_outstanding_invitation(self, pg_app, ab1_seed):
        client = pg_app.test_client()
        r = client.get(
            f"/api/envelopes/{ab1_seed['envelope'].id}/invitations",
            headers=_auth(ab1_seed["owner"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["envelope_id"] == ab1_seed["envelope"].id
        assert len(body["invitations"]) == 1
        row = body["invitations"][0]
        assert row["participant_id"] == ab1_seed["participant"].id
        assert row["consumed_at"] is None
        assert row["revoked_at"] is None
        assert row["reminder_count"] == 0

    def test_never_leaks_raw_token(self, pg_app, ab1_seed):
        client = pg_app.test_client()
        r = client.get(
            f"/api/envelopes/{ab1_seed['envelope'].id}/invitations",
            headers=_auth(ab1_seed["owner"]),
        )
        body = r.get_data(as_text=True)
        # Raw token never appears in the response payload.
        assert ab1_seed["raw_token"] not in body

    def test_cross_tenant_404(self, pg_app, ab1_seed):
        client = pg_app.test_client()
        r = client.get(
            f"/api/envelopes/{ab1_seed['envelope'].id}/invitations",
            headers=_auth(ab1_seed["intruder"]),
        )
        assert r.status_code == 404


# ============================================================ AB2 cancel delivery


@pytest.fixture
def ab2_seed(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.system import Role, UserRole
    from app.models.user import User
    from app.services import webhooks

    org = Organization(name="AB2 Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    role = Role.query.filter_by(name="admin").one_or_none() or Role(
        name="admin", description="test"
    )
    db.session.add(role)
    db.session.flush()
    owner = User(
        username="ab2-owner",
        email="ab2-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-ab-password-123")
    db.session.add(owner)
    db.session.flush()
    db.session.add(UserRole(user_id=owner.id, role_id=role.id))
    endpoint, _ = webhooks.register_endpoint(
        tenant_id=org.id,
        created_by_id=owner.id,
        url="https://example.test/ab2",
        events=["envelope.*"],
    )
    db.session.commit()
    deliveries = webhooks.fan_out_event(
        tenant_id=org.id,
        event_id="ab2-evt",
        event_type="envelope.prepared",
        payload={"envelope_id": 1},
    )
    db.session.commit()
    return {"org": org, "owner": owner, "endpoint": endpoint, "delivery": deliveries[0]}


class TestWebhookDeliveryCancel:
    def test_pending_delivery_cancelled(self, pg_app, ab2_seed):
        from app.extensions import db
        from app.models.webhook import WebhookDelivery

        client = pg_app.test_client()
        r = client.post(
            f"/api/webhooks/deliveries/{ab2_seed['delivery'].id}/cancel",
            headers=_auth(ab2_seed["owner"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["status"] == "dead"
        db.session.expire_all()
        refreshed = db.session.get(WebhookDelivery, ab2_seed["delivery"].id)
        assert refreshed.last_error == "operator_cancelled"

    def test_succeeded_delivery_rejected(self, pg_app, ab2_seed):
        from app.extensions import db

        ab2_seed["delivery"].status = "succeeded"
        ab2_seed["delivery"].completed_at = datetime.utcnow()
        db.session.commit()
        client = pg_app.test_client()
        r = client.post(
            f"/api/webhooks/deliveries/{ab2_seed['delivery'].id}/cancel",
            headers=_auth(ab2_seed["owner"]),
        )
        assert r.status_code == 409

    def test_already_dead_rejected(self, pg_app, ab2_seed):
        from app.extensions import db

        ab2_seed["delivery"].status = "dead"
        ab2_seed["delivery"].completed_at = datetime.utcnow()
        db.session.commit()
        client = pg_app.test_client()
        r = client.post(
            f"/api/webhooks/deliveries/{ab2_seed['delivery'].id}/cancel",
            headers=_auth(ab2_seed["owner"]),
        )
        assert r.status_code == 409

    def test_cross_tenant_404(self, pg_app, ab2_seed):
        from app.extensions import db
        from app.models.organization import Organization
        from app.models.user import User

        other_org = Organization(name="AB2 Other", type="company")
        db.session.add(other_org)
        db.session.flush()
        intruder = User(
            username="ab2-intruder",
            email="ab2-intruder@example.test",
            is_active=True,
            organization_id=other_org.id,
        )
        intruder.set_password("phase-ab-password-123")
        db.session.add(intruder)
        db.session.commit()
        client = pg_app.test_client()
        r = client.post(
            f"/api/webhooks/deliveries/{ab2_seed['delivery'].id}/cancel",
            headers=_auth(intruder),
        )
        assert r.status_code == 404
