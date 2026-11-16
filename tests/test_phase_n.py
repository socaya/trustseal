"""Phase N — scheduled operations + readiness."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token


# =========================================================== N1 expiry


@pytest.fixture
def envelope_seed(pg_app, tmp_path):
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

    org = Organization(name="Expiry Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    owner = User(
        username="exp-owner",
        email="exp-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("expirypassword12345")
    signer = User(
        username="exp-signer",
        email="exp-signer@example.test",
        is_active=True,
        organization_id=org.id,
    )
    signer.set_password("expirypassword12345")
    db.session.add_all([owner, signer])
    db.session.flush()
    doc = Document(
        title="Exp doc",
        status="draft",
        created_by=owner.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()
    body = b"%PDF-1.4\n% expiry\n%%EOF"
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
    db.session.flush()
    db.session.add(
        EnvelopeParticipant(
            envelope_id=envelope.id,
            user_id=signer.id,
            signing_order=1,
            role="signer",
        )
    )
    db.session.commit()
    return {
        "org": org,
        "owner": owner,
        "signer": signer,
        "envelope": envelope,
    }


class TestExpiry:
    def test_withdraws_prepared_without_decisions(
        self, pg_app, envelope_seed
    ):
        from app.extensions import db
        from app.models.signing_envelope import SigningEnvelope
        from app.services import envelope_expiry

        outcomes = envelope_expiry.cancel_expired_envelopes()
        db.session.commit()
        assert len(outcomes) == 1
        refreshed = db.session.get(
            SigningEnvelope, envelope_seed["envelope"].id
        )
        assert refreshed.state == "withdrawn"
        assert refreshed.withdraw_reason == "expired"

    def test_skips_envelope_with_decision(
        self, pg_app, envelope_seed
    ):
        from app.extensions import db
        from app.models.signer_decision import SignerChallenge, SignerDecision
        from app.services import envelope_expiry

        participant = envelope_seed["envelope"].id
        from app.models.signing_envelope import EnvelopeParticipant

        p = EnvelopeParticipant.query.filter_by(
            envelope_id=envelope_seed["envelope"].id
        ).one()
        challenge = SignerChallenge(
            envelope_id=envelope_seed["envelope"].id,
            participant_id=p.id,
            user_id=envelope_seed["signer"].id,
            document_sha256=envelope_seed["envelope"].document_sha256,
            nonce_sha256="n" * 64,
            issued_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=1),
            consumed_at=datetime.utcnow(),
        )
        db.session.add(challenge)
        db.session.flush()
        db.session.add(
            SignerDecision(
                envelope_id=envelope_seed["envelope"].id,
                participant_id=p.id,
                user_id=envelope_seed["signer"].id,
                challenge_id=challenge.id,
                decision="acknowledged",
                document_sha256=envelope_seed["envelope"].document_sha256,
                consent_version="review-intent-v1",
                consent_sha256="d" * 64,
                recorded_at=datetime.utcnow(),
            )
        )
        db.session.commit()
        outcomes = envelope_expiry.cancel_expired_envelopes()
        db.session.commit()
        assert outcomes == []


# =========================================================== N2 scanner


class TestReminderScanner:
    @pytest.fixture
    def seeded(self, pg_app, tmp_path):
        from app.extensions import db
        from app.models.documents.document import Document
        from app.models.documents.document_blob import DocumentBlob
        from app.models.organization import Organization
        from app.models.signer_invitation import SignerInvitation
        from app.models.signing_envelope import (
            EnvelopeParticipant,
            SigningEnvelope,
        )
        from app.models.user import User

        pg_app.config["PUBLIC_BASE_URL"] = "http://localhost.test"
        private_root = tmp_path / "private"
        private_root.mkdir(mode=0o700)
        pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)

        org = Organization(name="Scanner Tenant", type="company")
        db.session.add(org)
        db.session.flush()
        owner = User(
            username="scan-owner",
            email="scan-owner@example.test",
            is_active=True,
            organization_id=org.id,
        )
        owner.set_password("scannerpassword12345")
        signer = User(
            username="scan-signer",
            email="scan-signer@example.test",
            is_active=True,
            organization_id=org.id,
        )
        signer.set_password("scannerpassword12345")
        db.session.add_all([owner, signer])
        db.session.flush()
        doc = Document(
            title="Scan doc",
            status="draft",
            created_by=owner.id,
            organization_id=org.id,
        )
        db.session.add(doc)
        db.session.flush()
        body = b"%PDF-1.4\n% scanner\n%%EOF"
        digest = hashlib.sha256(body).hexdigest()
        (private_root / f"{digest}.pdf").write_bytes(body)
        blob = DocumentBlob(
            document_id=doc.id,
            revision=1,
            object_key=f"{digest}.pdf",
            file_name="scan.pdf",
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
        # Invitation expiring 24 hours from now — well inside the
        # 48-hour approaching window.
        invitation = SignerInvitation(
            envelope_id=envelope.id,
            participant_id=participant.id,
            user_id=signer.id,
            token_hash="t" * 64,
            issued_by_id=owner.id,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        db.session.add(invitation)
        db.session.commit()
        return {
            "org": org,
            "envelope": envelope,
            "participant": participant,
            "invitation": invitation,
            "signer": signer,
        }

    def test_sends_reminder_within_window(self, pg_app, seeded):
        from app.services import email as mailer
        from app.services import reminder_scanner

        mailer.clear_outbox()
        sent = reminder_scanner.scan_reminders()
        assert len(sent) == 1
        outbox = mailer.outbox()
        assert len(outbox) == 1
        assert outbox[0].to == seeded["signer"].email

    def test_second_scan_dedupes(self, pg_app, seeded):
        from app.extensions import db
        from app.services import reminder_scanner

        reminder_scanner.scan_reminders()
        db.session.commit()
        sent = reminder_scanner.scan_reminders()
        assert sent == []

    def test_cooloff_expires_allows_resend(self, pg_app, seeded):
        from app.extensions import db
        from app.services import reminder_scanner

        reminder_scanner.scan_reminders()
        db.session.commit()
        # Pretend the cool-off already elapsed.
        seeded["invitation"].last_reminder_at = (
            datetime.utcnow() - timedelta(hours=48)
        )
        db.session.commit()
        sent = reminder_scanner.scan_reminders(cooloff_hours=24)
        assert len(sent) == 1


# =========================================================== N3 health


class TestHealth:
    def test_health_returns_ok_unauthenticated(self, pg_app):
        client = pg_app.test_client()
        r = client.get("/health")
        assert r.status_code == 200
        assert r.get_json() == {"status": "ok"}

    def test_ready_reports_checks(self, pg_app):
        client = pg_app.test_client()
        r = client.get("/ready")
        # Mail transport is memory in tests, DB is up.
        body = r.get_json()
        assert "checks" in body
        statuses = {c["name"]: c["status"] for c in body["checks"]}
        assert statuses["database"] == "ok"
        assert statuses["mail_transport"] == "ok"

    def test_ready_fails_when_mail_transport_bogus(self, pg_app):
        pg_app.config["MAIL_TRANSPORT"] = "not-a-transport"
        try:
            client = pg_app.test_client()
            r = client.get("/ready")
            assert r.status_code == 503
            body = r.get_json()
            mail_check = [
                c for c in body["checks"] if c["name"] == "mail_transport"
            ][0]
            assert mail_check["status"] == "failed"
        finally:
            pg_app.config["MAIL_TRANSPORT"] = "memory"
