"""Phase R — per-envelope reminder cadence + archival."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token


@pytest.fixture
def phase_r_seed(pg_app, tmp_path):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.signing_envelope import SigningEnvelope
    from app.models.user import User

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)
    pg_app.config["PUBLIC_BASE_URL"] = "http://localhost.test"

    org = Organization(name="R Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    owner = User(
        username="r-owner",
        email="r-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-r-password-123")
    db.session.add(owner)
    db.session.flush()

    envelopes = []
    for n, state in enumerate(("draft", "withdrawn", "prepared")):
        doc = Document(
            title=f"R doc {n}",
            status="draft",
            created_by=owner.id,
            organization_id=org.id,
        )
        db.session.add(doc)
        db.session.flush()
        body = f"%PDF-1.4\n% r{n}\n%%EOF".encode()
        digest = hashlib.sha256(body).hexdigest()
        (private_root / f"{digest}.pdf").write_bytes(body)
        blob = DocumentBlob(
            document_id=doc.id,
            revision=1,
            object_key=f"{digest}.pdf",
            file_name=f"r{n}.pdf",
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
            state=state,
            prepared_at=(
                datetime.utcnow() if state == "prepared" else None
            ),
            withdrawn_at=(
                datetime.utcnow() if state == "withdrawn" else None
            ),
        )
        db.session.add(env)
        db.session.flush()
        envelopes.append(env)
    db.session.commit()
    return {"org": org, "owner": owner, "envelopes": envelopes}


# ============================================================ R1 cadence


class TestReminderCadence:
    def test_patch_sets_overrides(self, pg_app, phase_r_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(phase_r_seed["owner"].id))
        env = phase_r_seed["envelopes"][0]
        r = client.patch(
            f"/api/envelopes/{env.id}/reminders",
            json={"cooloff_hours": 12, "max_count": 5},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["cooloff_hours"] == 12
        assert body["max_count"] == 5

    def test_patch_rejects_out_of_range(self, pg_app, phase_r_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(phase_r_seed["owner"].id))
        env = phase_r_seed["envelopes"][0]
        headers = {"Authorization": f"Bearer {token}"}
        for bad in ({"cooloff_hours": 0}, {"cooloff_hours": 10000}, {"max_count": 0}, {"max_count": 51}):
            r = client.patch(
                f"/api/envelopes/{env.id}/reminders",
                json=bad,
                headers=headers,
            )
            assert r.status_code == 400, bad

    def test_patch_null_clears_override(self, pg_app, phase_r_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(phase_r_seed["owner"].id))
        env = phase_r_seed["envelopes"][0]
        headers = {"Authorization": f"Bearer {token}"}
        client.patch(
            f"/api/envelopes/{env.id}/reminders",
            json={"cooloff_hours": 6},
            headers=headers,
        )
        r = client.patch(
            f"/api/envelopes/{env.id}/reminders",
            json={"cooloff_hours": None},
            headers=headers,
        )
        assert r.status_code == 200
        assert r.get_json()["cooloff_hours"] is None

    def test_scanner_respects_envelope_cooloff(self, pg_app, tmp_path):
        """A short per-envelope cooloff should allow a resend sooner."""
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
        from app.services import email as mailer
        from app.services import reminder_scanner

        pg_app.config["PUBLIC_BASE_URL"] = "http://localhost.test"
        private_root = tmp_path / "private-cadence"
        private_root.mkdir(mode=0o700)
        pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)
        org = Organization(name="Cadence Tenant", type="company")
        db.session.add(org)
        db.session.flush()
        owner = User(
            username="cad-owner",
            email="cad-owner@example.test",
            is_active=True,
            organization_id=org.id,
        )
        owner.set_password("phase-r-password-123")
        signer = User(
            username="cad-signer",
            email="cad-signer@example.test",
            is_active=True,
            organization_id=org.id,
        )
        signer.set_password("phase-r-password-123")
        db.session.add_all([owner, signer])
        db.session.flush()
        doc = Document(
            title="Cadence doc",
            status="draft",
            created_by=owner.id,
            organization_id=org.id,
        )
        db.session.add(doc)
        db.session.flush()
        body = b"%PDF-1.4\n% cadence\n%%EOF"
        digest = hashlib.sha256(body).hexdigest()
        (private_root / f"{digest}.pdf").write_bytes(body)
        blob = DocumentBlob(
            document_id=doc.id,
            revision=1,
            object_key=f"{digest}.pdf",
            file_name="cad.pdf",
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
            reminder_cooloff_hours=1,  # override — 1 hour
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

        mailer.clear_outbox()
        first = reminder_scanner.scan_reminders()
        db.session.commit()
        assert len(first) == 1
        # Scanner default cooloff is 24h, but the envelope override
        # is 1h — pretend 90 minutes have passed.
        invitation.last_reminder_at = (
            datetime.utcnow() - timedelta(minutes=90)
        )
        db.session.commit()
        second = reminder_scanner.scan_reminders()
        db.session.commit()
        assert len(second) == 1

    def test_scanner_respects_max_count(self, pg_app, tmp_path):
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
        from app.services import email as mailer
        from app.services import reminder_scanner

        pg_app.config["PUBLIC_BASE_URL"] = "http://localhost.test"
        private_root = tmp_path / "private-maxcount"
        private_root.mkdir(mode=0o700)
        pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)
        org = Organization(name="MaxCount Tenant", type="company")
        db.session.add(org)
        db.session.flush()
        owner = User(
            username="mc-owner",
            email="mc-owner@example.test",
            is_active=True,
            organization_id=org.id,
        )
        owner.set_password("phase-r-password-123")
        signer = User(
            username="mc-signer",
            email="mc-signer@example.test",
            is_active=True,
            organization_id=org.id,
        )
        signer.set_password("phase-r-password-123")
        db.session.add_all([owner, signer])
        db.session.flush()
        doc = Document(
            title="MaxCount doc",
            status="draft",
            created_by=owner.id,
            organization_id=org.id,
        )
        db.session.add(doc)
        db.session.flush()
        body = b"%PDF-1.4\n% maxcount\n%%EOF"
        digest = hashlib.sha256(body).hexdigest()
        (private_root / f"{digest}.pdf").write_bytes(body)
        blob = DocumentBlob(
            document_id=doc.id,
            revision=1,
            object_key=f"{digest}.pdf",
            file_name="mc.pdf",
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
            reminder_cooloff_hours=1,
            reminder_max_count=1,
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

        mailer.clear_outbox()
        first = reminder_scanner.scan_reminders()
        db.session.commit()
        assert len(first) == 1
        # Shift the last-reminder back far enough that cooloff wouldn't
        # block. max_count is the only thing that should still block.
        invitation.last_reminder_at = (
            datetime.utcnow() - timedelta(hours=48)
        )
        db.session.commit()
        second = reminder_scanner.scan_reminders()
        db.session.commit()
        assert second == []


# ============================================================ R2 archival


class TestArchival:
    def test_archive_terminal_envelope(self, pg_app, phase_r_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(phase_r_seed["owner"].id))
        env = phase_r_seed["envelopes"][1]  # withdrawn
        r = client.post(
            f"/api/envelopes/{env.id}/archive",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["archived_at"] is not None
        assert body["archived_by_id"] == phase_r_seed["owner"].id

    def test_archive_blocked_for_active(self, pg_app, phase_r_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(phase_r_seed["owner"].id))
        env = phase_r_seed["envelopes"][2]  # prepared
        r = client.post(
            f"/api/envelopes/{env.id}/archive",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 409

    def test_default_list_hides_archived(self, pg_app, phase_r_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(phase_r_seed["owner"].id))
        headers = {"Authorization": f"Bearer {token}"}
        env = phase_r_seed["envelopes"][1]
        client.post(f"/api/envelopes/{env.id}/archive", headers=headers)
        listing = client.get("/api/envelopes", headers=headers).get_json()
        ids = {row["id"] for row in listing}
        assert env.id not in ids

    def test_include_archived_flag(self, pg_app, phase_r_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(phase_r_seed["owner"].id))
        headers = {"Authorization": f"Bearer {token}"}
        env = phase_r_seed["envelopes"][1]
        client.post(f"/api/envelopes/{env.id}/archive", headers=headers)
        listing = client.get(
            "/api/envelopes?include_archived=1", headers=headers
        ).get_json()
        ids = {row["id"] for row in listing}
        assert env.id in ids

    def test_unarchive_restores(self, pg_app, phase_r_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(phase_r_seed["owner"].id))
        headers = {"Authorization": f"Bearer {token}"}
        env = phase_r_seed["envelopes"][1]
        client.post(f"/api/envelopes/{env.id}/archive", headers=headers)
        r = client.post(
            f"/api/envelopes/{env.id}/unarchive", headers=headers
        )
        assert r.status_code == 200
        assert r.get_json()["archived_at"] is None
