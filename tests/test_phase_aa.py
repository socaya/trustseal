"""Phase AA — envelope participant removal + notification kind filter."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}


# ============================================================ AA1 participant delete


@pytest.fixture
def aa1_seed(pg_app, tmp_path):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.signing_envelope import (
        EnvelopeParticipant,
        SigningEnvelope,
    )
    from app.models.user import User

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)
    org = Organization(name="AA1 Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    owner = User(
        username="aa1-owner",
        email="aa1-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-aa-password-123")
    signer = User(
        username="aa1-signer",
        email="aa1-signer@example.test",
        is_active=True,
        organization_id=org.id,
    )
    signer.set_password("phase-aa-password-123")
    db.session.add_all([owner, signer])
    db.session.flush()
    doc = Document(
        title="AA1 doc",
        status="draft",
        created_by=owner.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()
    body = b"%PDF-1.4\n% aa1\n%%EOF"
    digest = hashlib.sha256(body).hexdigest()
    (private_root / f"{digest}.pdf").write_bytes(body)
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key=f"{digest}.pdf",
        file_name="aa1.pdf",
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
    db.session.flush()
    participant = EnvelopeParticipant(
        envelope_id=envelope.id,
        user_id=signer.id,
        signing_order=1,
        role="signer",
    )
    db.session.add(participant)
    db.session.commit()
    return {
        "org": org,
        "owner": owner,
        "signer": signer,
        "envelope": envelope,
        "participant": participant,
    }


class TestParticipantRemoval:
    def test_remove_draft_participant(self, pg_app, aa1_seed):
        from app.extensions import db
        from app.models.signing_envelope import EnvelopeParticipant

        client = pg_app.test_client()
        r = client.delete(
            f"/api/envelopes/{aa1_seed['envelope'].id}"
            f"/participants/{aa1_seed['participant'].id}",
            headers=_auth(aa1_seed["owner"]),
        )
        assert r.status_code == 200
        db.session.expire_all()
        assert (
            EnvelopeParticipant.query.filter_by(
                envelope_id=aa1_seed["envelope"].id
            ).count()
            == 0
        )

    def test_remove_after_prepared_rejected(self, pg_app, aa1_seed):
        from app.extensions import db

        aa1_seed["envelope"].state = "prepared"
        db.session.commit()
        client = pg_app.test_client()
        r = client.delete(
            f"/api/envelopes/{aa1_seed['envelope'].id}"
            f"/participants/{aa1_seed['participant'].id}",
            headers=_auth(aa1_seed["owner"]),
        )
        assert r.status_code == 409

    def test_remove_drops_outstanding_invitation(self, pg_app, aa1_seed):
        from app.extensions import db
        from app.models.signer_invitation import SignerInvitation
        from app.services import signer_invitations

        invitation, _ = signer_invitations.issue(
            envelope=aa1_seed["envelope"],
            participant=aa1_seed["participant"],
            issued_by_id=aa1_seed["owner"].id,
            lifetime=timedelta(hours=12),
        )
        db.session.commit()
        invitation_id = invitation.id
        client = pg_app.test_client()
        r = client.delete(
            f"/api/envelopes/{aa1_seed['envelope'].id}"
            f"/participants/{aa1_seed['participant'].id}",
            headers=_auth(aa1_seed["owner"]),
        )
        assert r.status_code == 200
        db.session.expire_all()
        # Invitation row was deleted alongside the participant.
        assert db.session.get(SignerInvitation, invitation_id) is None

    def test_unknown_participant_404(self, pg_app, aa1_seed):
        client = pg_app.test_client()
        r = client.delete(
            f"/api/envelopes/{aa1_seed['envelope'].id}/participants/99999",
            headers=_auth(aa1_seed["owner"]),
        )
        assert r.status_code == 404


# ============================================================ AA2 notification kind filter


@pytest.fixture
def aa2_seed(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.user import User
    from app.services import operator_notifications

    org = Organization(name="AA2 Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    actor = User(
        username="aa2-actor",
        email="aa2-actor@example.test",
        is_active=True,
        organization_id=org.id,
    )
    actor.set_password("phase-aa-password-123")
    db.session.add(actor)
    db.session.flush()
    for n in range(3):
        operator_notifications.publish(
            organization_id=org.id,
            recipient_user_id=actor.id,
            kind="envelope.sealed",
            subject_type="signing_envelope",
            subject_id=n,
            summary=f"sealed {n}",
        )
    for n in range(2):
        operator_notifications.publish(
            organization_id=org.id,
            recipient_user_id=actor.id,
            kind="webhook.delivery.dead",
            subject_type="webhook_delivery",
            subject_id=n,
            summary=f"dead {n}",
        )
    db.session.commit()
    return {"org": org, "actor": actor}


class TestNotificationKindFilter:
    def test_filter_by_kind(self, pg_app, aa2_seed):
        client = pg_app.test_client()
        r = client.get(
            "/api/notifications?kind=envelope.sealed",
            headers=_auth(aa2_seed["actor"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["kind"] == "envelope.sealed"
        assert len(body["notifications"]) == 3
        assert all(
            row["kind"] == "envelope.sealed" for row in body["notifications"]
        )

    def test_missing_kind_returns_all(self, pg_app, aa2_seed):
        client = pg_app.test_client()
        r = client.get(
            "/api/notifications",
            headers=_auth(aa2_seed["actor"]),
        )
        assert len(r.get_json()["notifications"]) == 5

    def test_kind_filter_combined_with_unread(self, pg_app, aa2_seed):
        from app.extensions import db
        from app.models.operator_notification import OperatorNotification

        # Mark one envelope.sealed as read.
        row = (
            OperatorNotification.query.filter_by(kind="envelope.sealed")
            .order_by(OperatorNotification.id.asc())
            .first()
        )
        row.read_at = datetime.utcnow()
        db.session.commit()
        client = pg_app.test_client()
        r = client.get(
            "/api/notifications?kind=envelope.sealed&unread=1",
            headers=_auth(aa2_seed["actor"]),
        )
        assert len(r.get_json()["notifications"]) == 2

    def test_bogus_kind_rejected(self, pg_app, aa2_seed):
        client = pg_app.test_client()
        r = client.get(
            "/api/notifications?kind=" + "x" * 61,
            headers=_auth(aa2_seed["actor"]),
        )
        assert r.status_code == 400
