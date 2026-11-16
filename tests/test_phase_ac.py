"""Phase AC — bulk reminder-all + invitation revocation."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}


@pytest.fixture
def phase_ac_seed(pg_app, tmp_path):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.signing_envelope import (
        EnvelopeParticipant,
        SigningEnvelope,
    )
    from app.models.user import User
    from app.services import signer_invitations as invitations_mod

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)
    pg_app.config["PUBLIC_BASE_URL"] = "http://localhost.test"

    org = Organization(name="AC Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    owner = User(
        username="ac-owner",
        email="ac-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-ac-password-123")
    db.session.add(owner)
    db.session.flush()
    signers = []
    for n in range(3):
        u = User(
            username=f"ac-signer-{n}",
            email=f"ac-signer-{n}@example.test",
            is_active=True,
            organization_id=org.id,
        )
        u.set_password("phase-ac-password-123")
        db.session.add(u)
        db.session.flush()
        signers.append(u)
    doc = Document(
        title="AC doc",
        status="draft",
        created_by=owner.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()
    body = b"%PDF-1.4\n% ac\n%%EOF"
    digest = hashlib.sha256(body).hexdigest()
    (private_root / f"{digest}.pdf").write_bytes(body)
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key=f"{digest}.pdf",
        file_name="ac.pdf",
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
    participants = []
    invitations = []
    for idx, s in enumerate(signers):
        p = EnvelopeParticipant(
            envelope_id=envelope.id,
            user_id=s.id,
            signing_order=idx + 1,
            role="signer",
        )
        db.session.add(p)
        db.session.flush()
        participants.append(p)
        inv, _ = invitations_mod.issue(
            envelope=envelope,
            participant=p,
            issued_by_id=owner.id,
            lifetime=timedelta(hours=24),
        )
        invitations.append(inv)
    db.session.commit()
    return {
        "org": org,
        "owner": owner,
        "signers": signers,
        "envelope": envelope,
        "participants": participants,
        "invitations": invitations,
    }


# ============================================================ AC1 reminder-all


class TestBulkReminderAll:
    def test_sends_to_all_unacknowledged(self, pg_app, phase_ac_seed):
        from app.services import email as mailer

        mailer.clear_outbox()
        client = pg_app.test_client()
        r = client.post(
            f"/api/envelopes/{phase_ac_seed['envelope'].id}/reminders/send-all",
            headers=_auth(phase_ac_seed["owner"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["sent"] == 3
        assert len(mailer.outbox()) == 3

    def test_skips_participants_with_decisions(
        self, pg_app, phase_ac_seed
    ):
        from app.extensions import db
        from app.models.signer_decision import SignerChallenge, SignerDecision
        from app.services import email as mailer

        # Simulate one participant having decided already.
        first = phase_ac_seed["participants"][0]
        challenge = SignerChallenge(
            envelope_id=phase_ac_seed["envelope"].id,
            participant_id=first.id,
            user_id=first.user_id,
            document_sha256=phase_ac_seed["envelope"].document_sha256,
            nonce_sha256="n" * 64,
            issued_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=5),
            consumed_at=datetime.utcnow(),
        )
        db.session.add(challenge)
        db.session.flush()
        db.session.add(
            SignerDecision(
                envelope_id=phase_ac_seed["envelope"].id,
                participant_id=first.id,
                user_id=first.user_id,
                challenge_id=challenge.id,
                decision="acknowledged",
                document_sha256=phase_ac_seed["envelope"].document_sha256,
                consent_version="review-intent-v1",
                consent_sha256="d" * 64,
                recorded_at=datetime.utcnow(),
            )
        )
        db.session.commit()
        mailer.clear_outbox()
        client = pg_app.test_client()
        r = client.post(
            f"/api/envelopes/{phase_ac_seed['envelope'].id}/reminders/send-all",
            headers=_auth(phase_ac_seed["owner"]),
        )
        body = r.get_json()
        assert body["sent"] == 2
        skipped = [r for r in body["results"] if r["status"] == "skipped"]
        assert len(skipped) == 1
        assert skipped[0]["reason"] == "already_decided"

    def test_non_prepared_rejected(self, pg_app, phase_ac_seed):
        from app.extensions import db

        phase_ac_seed["envelope"].state = "draft"
        db.session.commit()
        client = pg_app.test_client()
        r = client.post(
            f"/api/envelopes/{phase_ac_seed['envelope'].id}/reminders/send-all",
            headers=_auth(phase_ac_seed["owner"]),
        )
        assert r.status_code == 409


# ============================================================ AC2 revoke invitation


class TestRevokeInvitation:
    def test_revokes_outstanding(self, pg_app, phase_ac_seed):
        from app.extensions import db
        from app.models.signer_invitation import SignerInvitation

        client = pg_app.test_client()
        inv = phase_ac_seed["invitations"][0]
        r = client.post(
            f"/api/envelopes/{phase_ac_seed['envelope'].id}"
            f"/invitations/{inv.id}/revoke",
            json={"reason": "incorrect_recipient"},
            headers=_auth(phase_ac_seed["owner"]),
        )
        assert r.status_code == 200
        db.session.expire_all()
        refreshed = db.session.get(SignerInvitation, inv.id)
        assert refreshed.revoked_at is not None
        assert refreshed.revoke_reason == "incorrect_recipient"

    def test_revoke_without_reason_uses_default(
        self, pg_app, phase_ac_seed
    ):
        from app.extensions import db
        from app.models.signer_invitation import SignerInvitation

        client = pg_app.test_client()
        inv = phase_ac_seed["invitations"][0]
        r = client.post(
            f"/api/envelopes/{phase_ac_seed['envelope'].id}"
            f"/invitations/{inv.id}/revoke",
            headers=_auth(phase_ac_seed["owner"]),
        )
        assert r.status_code == 200
        db.session.expire_all()
        refreshed = db.session.get(SignerInvitation, inv.id)
        assert refreshed.revoke_reason == "operator_revoked"

    def test_already_revoked_rejected(self, pg_app, phase_ac_seed):
        from app.extensions import db

        phase_ac_seed["invitations"][0].revoked_at = datetime.utcnow()
        phase_ac_seed["invitations"][0].revoke_reason = "prior"
        db.session.commit()
        client = pg_app.test_client()
        r = client.post(
            f"/api/envelopes/{phase_ac_seed['envelope'].id}"
            f"/invitations/{phase_ac_seed['invitations'][0].id}/revoke",
            headers=_auth(phase_ac_seed["owner"]),
        )
        assert r.status_code == 409

    def test_consumed_invitation_rejected(self, pg_app, phase_ac_seed):
        from app.extensions import db

        phase_ac_seed["invitations"][0].consumed_at = datetime.utcnow()
        db.session.commit()
        client = pg_app.test_client()
        r = client.post(
            f"/api/envelopes/{phase_ac_seed['envelope'].id}"
            f"/invitations/{phase_ac_seed['invitations'][0].id}/revoke",
            headers=_auth(phase_ac_seed["owner"]),
        )
        assert r.status_code == 409

    def test_unknown_invitation_404(self, pg_app, phase_ac_seed):
        client = pg_app.test_client()
        r = client.post(
            f"/api/envelopes/{phase_ac_seed['envelope'].id}"
            f"/invitations/9999999/revoke",
            headers=_auth(phase_ac_seed["owner"]),
        )
        assert r.status_code == 404
