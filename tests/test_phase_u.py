"""Phase U — signer supporting attachments."""
from __future__ import annotations

import hashlib
import io
import secrets
from datetime import datetime, timedelta

import pytest


_PNG_HEADER = b"\x89PNG\r\n\x1a\n"


def _png_bytes(body: bytes = b"phase-u-test-png") -> bytes:
    """A minimal byte string that starts with the PNG magic."""
    return _PNG_HEADER + body


def _pdf_bytes(label: str = "phase-u") -> bytes:
    return b"%PDF-1.4\n% " + label.encode() + b"\n%%EOF"


@pytest.fixture
def phase_u_seed(pg_app, tmp_path):
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
    from app.services import signer_invitations as invitations_mod

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)
    pg_app.config["PUBLIC_BASE_URL"] = "http://localhost.test"
    pg_app.config["PRIVATE_STORAGE_BACKEND"] = "filesystem"

    org = Organization(name="U Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    owner = User(
        username="u-owner",
        email="u-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-u-password-123")
    signer = User(
        username="u-signer",
        email="u-signer@example.test",
        is_active=True,
        organization_id=org.id,
    )
    signer.set_password("phase-u-password-123")
    db.session.add_all([owner, signer])
    db.session.flush()
    doc = Document(
        title="U doc",
        status="draft",
        created_by=owner.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()
    body = _pdf_bytes("u")
    digest = hashlib.sha256(body).hexdigest()
    (private_root / f"{digest}.pdf").write_bytes(body)
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key=f"{digest}.pdf",
        file_name="u.pdf",
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
    # Mint an invitation via the service so the token-hash matches.
    invitation, raw_token = invitations_mod.issue(
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
        "envelope": envelope,
        "participant": participant,
        "invitation": invitation,
        "token": raw_token,
    }


# ============================================================ U1 upload


class TestAttachmentUpload:
    def test_upload_png_round_trip(self, pg_app, phase_u_seed):
        from app.extensions import db
        from app.models.signer_attachment import SignerAttachment

        client = pg_app.test_client()
        payload = _png_bytes(secrets.token_bytes(64))
        data = {
            "file": (io.BytesIO(payload), "evidence.png", "image/png"),
        }
        r = client.post(
            f"/sign/{phase_u_seed['token']}/attachments",
            data=data,
            content_type="multipart/form-data",
        )
        assert r.status_code == 201, r.get_data(as_text=True)
        body = r.get_json()
        assert body["sha256"] == hashlib.sha256(payload).hexdigest()
        assert body["mime_type"] == "image/png"
        db.session.expire_all()
        row = db.session.get(SignerAttachment, body["id"])
        assert row is not None
        assert row.decision_id is None  # staged
        assert row.envelope_id == phase_u_seed["envelope"].id
        assert row.participant_id == phase_u_seed["participant"].id

    def test_upload_rejects_fake_mime(self, pg_app, phase_u_seed):
        client = pg_app.test_client()
        # Says PNG but the bytes are text.
        data = {
            "file": (io.BytesIO(b"not-really-a-png"), "x.png", "image/png"),
        }
        r = client.post(
            f"/sign/{phase_u_seed['token']}/attachments",
            data=data,
            content_type="multipart/form-data",
        )
        assert r.status_code == 400
        assert r.get_json()["error"] == "magic_bytes_mismatch"

    def test_upload_rejects_disallowed_mime(self, pg_app, phase_u_seed):
        client = pg_app.test_client()
        data = {
            "file": (io.BytesIO(b"GIF89aXXX"), "a.gif", "image/gif"),
        }
        r = client.post(
            f"/sign/{phase_u_seed['token']}/attachments",
            data=data,
            content_type="multipart/form-data",
        )
        assert r.status_code == 400
        assert r.get_json()["error"] == "mime_not_allowed"

    def test_upload_rejects_payload_over_limit(self, pg_app, phase_u_seed):
        client = pg_app.test_client()
        huge = _PNG_HEADER + b"\x00" * (10 * 1024 * 1024 + 1)
        data = {
            "file": (io.BytesIO(huge), "huge.png", "image/png"),
        }
        r = client.post(
            f"/sign/{phase_u_seed['token']}/attachments",
            data=data,
            content_type="multipart/form-data",
        )
        assert r.status_code == 400
        assert r.get_json()["error"] == "payload_too_large"

    def test_bad_token_returns_unavailable(self, pg_app, phase_u_seed):
        client = pg_app.test_client()
        data = {
            "file": (io.BytesIO(_png_bytes()), "x.png", "image/png"),
        }
        r = client.post(
            "/sign/not-a-real-token/attachments",
            data=data,
            content_type="multipart/form-data",
        )
        assert r.status_code == 404


# ============================================================ U2 decision + receipt


class TestDecisionAttachmentBinding:
    def _upload(self, client, token, payload: bytes, mime: str, name: str):
        data = {
            "file": (io.BytesIO(payload), name, mime),
        }
        r = client.post(
            f"/sign/{token}/attachments",
            data=data,
            content_type="multipart/form-data",
        )
        assert r.status_code == 201, r.get_data(as_text=True)
        return r.get_json()["id"]

    def test_decision_binds_attachments(self, pg_app, phase_u_seed):
        from app.extensions import db
        from app.models.signer_attachment import SignerAttachment
        from app.models.signer_decision import SignerDecision

        client = pg_app.test_client()
        token = phase_u_seed["token"]
        a_id = self._upload(
            client, token, _png_bytes(b"evidence-a"), "image/png", "a.png"
        )
        b_id = self._upload(
            client, token, _pdf_bytes("evidence-b"), "application/pdf", "b.pdf"
        )
        r = client.post(
            f"/sign/{token}/decision",
            data={
                "choice": "acknowledged",
                "attachment_ids": f"{a_id},{b_id}",
            },
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        db.session.expire_all()
        decision = SignerDecision.query.filter_by(
            participant_id=phase_u_seed["participant"].id
        ).one()
        rows = SignerAttachment.query.filter_by(
            decision_id=decision.id
        ).all()
        assert {r.id for r in rows} == {a_id, b_id}

    def test_cross_participant_attachment_rolls_back(
        self, pg_app, phase_u_seed
    ):
        """A signer must not be able to claim another signer's attachment."""
        from app.extensions import db
        from app.models.organization import Organization
        from app.models.signer_attachment import SignerAttachment
        from app.models.signer_decision import SignerDecision
        from app.models.signing_envelope import (
            EnvelopeParticipant,
            SigningEnvelope,
        )
        from app.models.user import User
        from app.services import signer_invitations as invitations_mod

        # Create a second envelope in the same tenant, upload an
        # attachment there, then try to claim it from the first
        # envelope's signer session.
        other_signer = User(
            username="u-other",
            email="u-other@example.test",
            is_active=True,
            organization_id=phase_u_seed["org"].id,
        )
        other_signer.set_password("phase-u-password-123")
        db.session.add(other_signer)
        db.session.flush()
        other_env = SigningEnvelope(
            organization_id=phase_u_seed["org"].id,
            document_id=phase_u_seed["envelope"].document_id,
            document_blob_id=phase_u_seed["envelope"].document_blob_id,
            document_sha256=phase_u_seed["envelope"].document_sha256,
            created_by_id=phase_u_seed["owner"].id,
            state="prepared",
            prepared_at=datetime.utcnow(),
        )
        db.session.add(other_env)
        db.session.flush()
        other_part = EnvelopeParticipant(
            envelope_id=other_env.id,
            user_id=other_signer.id,
            signing_order=1,
            role="signer",
        )
        db.session.add(other_part)
        db.session.flush()
        _, other_token = invitations_mod.issue(
            envelope=other_env,
            participant=other_part,
            issued_by_id=phase_u_seed["owner"].id,
            lifetime=timedelta(hours=12),
        )
        db.session.commit()
        client = pg_app.test_client()
        other_id = self._upload(
            client,
            other_token,
            _png_bytes(b"cross-env"),
            "image/png",
            "cross.png",
        )
        # Now the first signer tries to attach the other signer's id.
        r = client.post(
            f"/sign/{phase_u_seed['token']}/decision",
            data={
                "choice": "acknowledged",
                "attachment_ids": str(other_id),
            },
        )
        # Flash + redirect on failure.
        assert r.status_code == 302
        db.session.expire_all()
        # No decision recorded for the first participant.
        assert (
            SignerDecision.query.filter_by(
                participant_id=phase_u_seed["participant"].id
            ).count()
            == 0
        )
        # The other envelope's attachment remains unbound.
        cross_row = db.session.get(SignerAttachment, other_id)
        assert cross_row.decision_id is None

    def test_receipt_includes_attachments(self, pg_app, phase_u_seed):
        from app.extensions import db
        from app.models.signer_decision import SignerDecision
        from app.services import signing_receipts

        client = pg_app.test_client()
        token = phase_u_seed["token"]
        a_id = self._upload(
            client, token, _png_bytes(b"receipt-a"), "image/png", "ra.png"
        )
        client.post(
            f"/sign/{token}/decision",
            data={
                "choice": "acknowledged",
                "attachment_ids": str(a_id),
            },
        )
        db.session.expire_all()
        decision = SignerDecision.query.filter_by(
            participant_id=phase_u_seed["participant"].id
        ).one()
        payload = signing_receipts.review_payload(
            envelope=phase_u_seed["envelope"],
            participant=phase_u_seed["participant"],
            decision=decision,
        )
        assert "attachments" in payload
        assert len(payload["attachments"]) == 1
        assert payload["attachments"][0]["sha256"] == hashlib.sha256(
            _png_bytes(b"receipt-a")
        ).hexdigest()

    def test_receipt_omits_attachments_when_none(self, pg_app, phase_u_seed):
        from app.extensions import db
        from app.models.signer_decision import SignerDecision
        from app.services import signing_receipts

        client = pg_app.test_client()
        client.post(
            f"/sign/{phase_u_seed['token']}/decision",
            data={"choice": "acknowledged"},
        )
        db.session.expire_all()
        decision = SignerDecision.query.filter_by(
            participant_id=phase_u_seed["participant"].id
        ).one()
        payload = signing_receipts.review_payload(
            envelope=phase_u_seed["envelope"],
            participant=phase_u_seed["participant"],
            decision=decision,
        )
        # The field must be absent so legacy receipts stay stable.
        assert "attachments" not in payload
