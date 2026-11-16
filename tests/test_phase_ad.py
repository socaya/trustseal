"""Phase AD — attachment SHA-256 lookup + signer status poll."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}


# ============================================================ AD1 attachment lookup


@pytest.fixture
def ad1_seed(pg_app, tmp_path):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.signer_attachment import SignerAttachment
    from app.models.signer_decision import SignerChallenge, SignerDecision
    from app.models.signing_envelope import (
        EnvelopeParticipant,
        SigningEnvelope,
    )
    from app.models.user import User
    from app.services.documents.private_object_store import active_store

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)
    pg_app.config["PRIVATE_STORAGE_BACKEND"] = "filesystem"

    org = Organization(name="AD1 Tenant", type="company")
    other_org = Organization(name="AD1 Other", type="company")
    db.session.add_all([org, other_org])
    db.session.flush()
    owner = User(
        username="ad1-owner",
        email="ad1-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-ad-password-123")
    signer = User(
        username="ad1-signer",
        email="ad1-signer@example.test",
        is_active=True,
        organization_id=org.id,
    )
    signer.set_password("phase-ad-password-123")
    intruder = User(
        username="ad1-intruder",
        email="ad1-intruder@example.test",
        is_active=True,
        organization_id=other_org.id,
    )
    intruder.set_password("phase-ad-password-123")
    db.session.add_all([owner, signer, intruder])
    db.session.flush()
    doc = Document(
        title="AD1 doc",
        status="draft",
        created_by=owner.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()
    body = b"%PDF-1.4\n% ad1\n%%EOF"
    digest = hashlib.sha256(body).hexdigest()
    (private_root / f"{digest}.pdf").write_bytes(body)
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key=f"{digest}.pdf",
        file_name="ad1.pdf",
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

    store = active_store(pg_app.config)
    bound_payload = b"\x89PNG\r\n\x1a\nbound-attachment"
    staged_payload = b"\x89PNG\r\n\x1a\nstaged-attachment"
    bound_res = store.put(bound_payload, config=pg_app.config)
    staged_res = store.put(staged_payload, config=pg_app.config)
    bound = SignerAttachment(
        envelope_id=envelope.id,
        participant_id=participant.id,
        user_id=signer.id,
        decision_id=decision.id,
        organization_id=org.id,
        object_key=bound_res.key,
        file_name="bound.png",
        mime_type="image/png",
        file_size=bound_res.size,
        sha256=bound_res.sha256,
        scanner="noop",
    )
    staged = SignerAttachment(
        envelope_id=envelope.id,
        participant_id=participant.id,
        user_id=signer.id,
        organization_id=org.id,
        object_key=staged_res.key,
        file_name="staged.png",
        mime_type="image/png",
        file_size=staged_res.size,
        sha256=staged_res.sha256,
        scanner="noop",
    )
    db.session.add_all([bound, staged])
    db.session.commit()
    return {
        "org": org,
        "other_org": other_org,
        "owner": owner,
        "intruder": intruder,
        "envelope": envelope,
        "bound": bound,
        "staged": staged,
    }


class TestAttachmentLookup:
    def test_find_bound_attachment(self, pg_app, ad1_seed):
        client = pg_app.test_client()
        r = client.get(
            f"/api/signer-attachments/by-sha256/{ad1_seed['bound'].sha256}",
            headers=_auth(ad1_seed["owner"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["found"] == 1
        assert body["attachments"][0]["envelope_id"] == ad1_seed["envelope"].id

    def test_staged_attachment_hidden(self, pg_app, ad1_seed):
        client = pg_app.test_client()
        r = client.get(
            f"/api/signer-attachments/by-sha256/{ad1_seed['staged'].sha256}",
            headers=_auth(ad1_seed["owner"]),
        )
        assert r.status_code == 200
        assert r.get_json()["found"] == 0

    def test_cross_tenant_hidden(self, pg_app, ad1_seed):
        client = pg_app.test_client()
        r = client.get(
            f"/api/signer-attachments/by-sha256/{ad1_seed['bound'].sha256}",
            headers=_auth(ad1_seed["intruder"]),
        )
        assert r.status_code == 200
        assert r.get_json()["found"] == 0

    def test_invalid_digest_rejected(self, pg_app, ad1_seed):
        client = pg_app.test_client()
        r = client.get(
            "/api/signer-attachments/by-sha256/not-a-digest",
            headers=_auth(ad1_seed["owner"]),
        )
        assert r.status_code == 400


# ============================================================ AD2 signer status


@pytest.fixture
def ad2_seed(pg_app, tmp_path):
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

    org = Organization(name="AD2 Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    owner = User(
        username="ad2-owner",
        email="ad2-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-ad-password-123")
    signer = User(
        username="ad2-signer",
        email="ad2-signer@example.test",
        is_active=True,
        organization_id=org.id,
    )
    signer.set_password("phase-ad-password-123")
    db.session.add_all([owner, signer])
    db.session.flush()
    doc = Document(
        title="AD2 doc",
        status="draft",
        created_by=owner.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()
    body = b"%PDF-1.4\n% ad2\n%%EOF"
    digest = hashlib.sha256(body).hexdigest()
    (private_root / f"{digest}.pdf").write_bytes(body)
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key=f"{digest}.pdf",
        file_name="ad2.pdf",
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


class TestSignerStatus:
    def test_returns_pending_status(self, pg_app, ad2_seed):
        client = pg_app.test_client()
        r = client.get(f"/sign/{ad2_seed['token']}/status")
        assert r.status_code == 200
        body = r.get_json()
        assert body["envelope_id"] == ad2_seed["envelope"].id
        assert body["decision_recorded"] is False
        assert body["signing_order"] == 1

    def test_reports_decision_when_recorded(self, pg_app, ad2_seed):
        from app.extensions import db
        from app.models.signer_decision import SignerChallenge, SignerDecision

        challenge = SignerChallenge(
            envelope_id=ad2_seed["envelope"].id,
            participant_id=ad2_seed["participant"].id,
            user_id=ad2_seed["signer"].id,
            document_sha256=ad2_seed["envelope"].document_sha256,
            nonce_sha256="n" * 64,
            issued_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=5),
            consumed_at=datetime.utcnow(),
        )
        db.session.add(challenge)
        db.session.flush()
        db.session.add(
            SignerDecision(
                envelope_id=ad2_seed["envelope"].id,
                participant_id=ad2_seed["participant"].id,
                user_id=ad2_seed["signer"].id,
                challenge_id=challenge.id,
                decision="acknowledged",
                document_sha256=ad2_seed["envelope"].document_sha256,
                consent_version="review-intent-v1",
                consent_sha256="d" * 64,
                recorded_at=datetime.utcnow(),
            )
        )
        db.session.commit()
        client = pg_app.test_client()
        r = client.get(f"/sign/{ad2_seed['token']}/status")
        body = r.get_json()
        assert body["decision_recorded"] is True
        assert body["decision"] == "acknowledged"

    def test_bad_token_404(self, pg_app, ad2_seed):
        client = pg_app.test_client()
        r = client.get("/sign/does-not-exist/status")
        assert r.status_code == 404

    def test_revoked_token_404(self, pg_app, ad2_seed):
        from app.extensions import db

        ad2_seed["invitation"].revoked_at = datetime.utcnow()
        ad2_seed["invitation"].revoke_reason = "operator_revoked"
        db.session.commit()
        client = pg_app.test_client()
        r = client.get(f"/sign/{ad2_seed['token']}/status")
        assert r.status_code == 404

    def test_status_does_not_consume_invitation(self, pg_app, ad2_seed):
        from app.extensions import db
        from app.models.signer_invitation import SignerInvitation

        client = pg_app.test_client()
        client.get(f"/sign/{ad2_seed['token']}/status")
        db.session.expire_all()
        refreshed = db.session.get(SignerInvitation, ad2_seed["invitation"].id)
        assert refreshed.consumed_at is None
