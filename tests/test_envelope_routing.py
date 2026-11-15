"""Envelope routing modes + exception flows + preview checkpoint (C3+C4+C5).

Covers:

C3 — routing modes:
* Creating with each mode (sequential, parallel, quorum) persists the
  choice.
* Quorum envelopes must specify ``quorum_required``.
* Signer eligibility (``_eligible``) honours the mode:
  - sequential: earlier-order participants must have acknowledged.
  - parallel: any order; a witness waits for every signer.
  - quorum: any signer order; a witness waits for the quorum target.

C4 — exception flows:
* ``POST /api/envelopes/<id>/withdraw`` transitions prepared →
  withdrawn before any decision lands.
* Withdraw refuses once a participant has acknowledged.
* ``POST /api/envelopes/<id>/participants/<pid>/reminder`` sends a
  reminder email via the in-memory outbox.
* ``POST /api/envelopes/<id>/participants/<pid>/resend-invitation``
  revokes the active invitation and issues a new token.

C5 — preview checkpoint:
* ``POST /api/envelopes/<id>/preview/confirm`` stamps
  ``preview_confirmed_at``.
* ``/prepare`` refuses with 409 if no confirmation yet.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from flask_jwt_extended import create_access_token


@pytest.fixture
def seeded(pg_app, tmp_path):
    """Envelope with three signers + one witness and a valid PDF blob."""
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.signing_envelope import EnvelopeParticipant, SigningEnvelope
    from app.models.user import User

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)

    org = Organization(name="Routing Tenant", type="company")
    db.session.add(org)
    db.session.flush()

    def mk(username, email):
        u = User(
            username=username,
            email=email,
            is_active=True,
            organization_id=org.id,
        )
        u.set_password("routingpassword12345")
        db.session.add(u)
        db.session.flush()
        return u

    creator = mk("routing-creator", "routing-creator@example.test")
    signer_a = mk("routing-signer-a", "routing-signer-a@example.test")
    signer_b = mk("routing-signer-b", "routing-signer-b@example.test")
    signer_c = mk("routing-signer-c", "routing-signer-c@example.test")
    witness = mk("routing-witness", "routing-witness@example.test")

    doc = Document(
        title="Routing doc",
        status="draft",
        created_by=creator.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()
    body = b"%PDF-1.4\n% routing test\n%%EOF"
    digest = hashlib.sha256(body).hexdigest()
    (Path(private_root) / f"{digest}.pdf").write_bytes(body)
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key=f"{digest}.pdf",
        file_name="routing.pdf",
        mime_type="application/pdf",
        file_size=len(body),
        sha256=digest,
        scanner="noop",
        created_by_id=creator.id,
    )
    db.session.add(blob)
    db.session.commit()
    return {
        "org": org,
        "creator": creator,
        "signer_a": signer_a,
        "signer_b": signer_b,
        "signer_c": signer_c,
        "witness": witness,
        "doc": doc,
        "blob": blob,
    }


def _mk_envelope(
    pg_app, seeded, *, routing_mode="sequential", quorum_required=None,
    include_witness=False, n_signers=3,
):
    """Create a draft envelope with participants via the service layer."""
    from app.extensions import db
    from app.models.signing_envelope import (
        EnvelopeParticipant, SigningEnvelope,
    )

    envelope = SigningEnvelope(
        organization_id=seeded["org"].id,
        document_id=seeded["doc"].id,
        document_blob_id=seeded["blob"].id,
        document_sha256=seeded["blob"].sha256,
        created_by_id=seeded["creator"].id,
        state="draft",
        routing_mode=routing_mode,
        quorum_required=quorum_required,
    )
    db.session.add(envelope)
    db.session.flush()
    order = 1
    participants = {}
    for key in ("signer_a", "signer_b", "signer_c")[:n_signers]:
        p = EnvelopeParticipant(
            envelope_id=envelope.id,
            user_id=seeded[key].id,
            signing_order=order,
            role="signer",
        )
        db.session.add(p)
        db.session.flush()
        participants[key] = p
        order += 1
    if include_witness:
        w = EnvelopeParticipant(
            envelope_id=envelope.id,
            user_id=seeded["witness"].id,
            signing_order=order,
            role="witness",
        )
        db.session.add(w)
        db.session.flush()
        participants["witness"] = w
    db.session.commit()
    return envelope, participants


def _issue_and_decide(pg_app, envelope, participant, user, password):
    """HTTP helper: go through challenge + decision."""
    client = pg_app.test_client()
    token = create_access_token(identity=str(user.id))
    r = client.post(
        f"/api/signer-intent/envelopes/{envelope.id}/challenge",
        json={"password": password},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.get_data(as_text=True)
    body = r.get_json()
    r = client.post(
        f"/api/signer-intent/envelopes/{envelope.id}/decision",
        json={
            "challenge_id": body["challenge_id"],
            "challenge": body["challenge"],
            "decision": "acknowledged",
            "document_sha256": envelope.document_sha256,
            "consent_version": "review-intent-v1",
            "affirmed": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    return r


class TestRoutingModes:
    def test_create_with_parallel_mode(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["creator"].id))
        r = client.post(
            "/api/envelopes",
            json={
                "document_id": seeded["doc"].id,
                "document_blob_id": seeded["blob"].id,
                "routing_mode": "parallel",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        assert r.get_json()["routing_mode"] == "parallel"

    def test_quorum_mode_requires_quorum_required(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["creator"].id))
        r = client.post(
            "/api/envelopes",
            json={
                "document_id": seeded["doc"].id,
                "document_blob_id": seeded["blob"].id,
                "routing_mode": "quorum",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400

    def test_parallel_eligibility_allows_any_order(self, pg_app, seeded):
        from app.extensions import db

        envelope, participants = _mk_envelope(
            pg_app, seeded, routing_mode="parallel"
        )
        # Mark prepared manually (we're testing eligibility, not prep).
        envelope.state = "prepared"
        envelope.prepared_at = datetime.utcnow()
        db.session.commit()
        # The second signer can go first in parallel mode.
        r = _issue_and_decide(
            pg_app,
            envelope,
            participants["signer_b"],
            seeded["signer_b"],
            "routingpassword12345",
        )
        assert r.status_code == 201, r.get_data(as_text=True)

    def test_sequential_blocks_out_of_order(self, pg_app, seeded):
        from app.extensions import db

        envelope, participants = _mk_envelope(
            pg_app, seeded, routing_mode="sequential"
        )
        envelope.state = "prepared"
        envelope.prepared_at = datetime.utcnow()
        db.session.commit()
        # signer_b (order=2) cannot go before signer_a (order=1).
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["signer_b"].id))
        r = client.post(
            f"/api/signer-intent/envelopes/{envelope.id}/challenge",
            json={"password": "routingpassword12345"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 409

    def test_witness_waits_for_quorum(self, pg_app, seeded):
        from app.extensions import db

        envelope, participants = _mk_envelope(
            pg_app,
            seeded,
            routing_mode="quorum",
            quorum_required=2,
            include_witness=True,
        )
        envelope.state = "prepared"
        envelope.prepared_at = datetime.utcnow()
        db.session.commit()
        # Witness before any signer should be refused.
        client = pg_app.test_client()
        wtoken = create_access_token(identity=str(seeded["witness"].id))
        r = client.post(
            f"/api/signer-intent/envelopes/{envelope.id}/challenge",
            json={"password": "routingpassword12345"},
            headers={"Authorization": f"Bearer {wtoken}"},
        )
        assert r.status_code == 409
        # Two signers acknowledge → quorum reached → witness admitted.
        for key in ("signer_a", "signer_b"):
            r = _issue_and_decide(
                pg_app,
                envelope,
                participants[key],
                seeded[key],
                "routingpassword12345",
            )
            assert r.status_code == 201
        r = client.post(
            f"/api/signer-intent/envelopes/{envelope.id}/challenge",
            json={"password": "routingpassword12345"},
            headers={"Authorization": f"Bearer {wtoken}"},
        )
        assert r.status_code == 201, r.get_data(as_text=True)


class TestPreviewCheckpoint:
    def test_prepare_refuses_without_preview(self, pg_app, seeded):
        from app.extensions import db

        envelope, _ = _mk_envelope(pg_app, seeded)
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["creator"].id))
        r = client.post(
            f"/api/envelopes/{envelope.id}/prepare",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"prep-{envelope.id}-1",
            },
        )
        assert r.status_code == 409
        assert "preview" in r.get_data(as_text=True)

    def test_preview_confirm_then_prepare(self, pg_app, seeded):
        envelope, _ = _mk_envelope(pg_app, seeded)
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["creator"].id))
        r = client.post(
            f"/api/envelopes/{envelope.id}/preview/confirm",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"preview-{envelope.id}-1",
            },
        )
        assert r.status_code == 200
        assert r.get_json()["preview_confirmed_at"] is not None
        r = client.post(
            f"/api/envelopes/{envelope.id}/prepare",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"prep-{envelope.id}-2",
            },
        )
        assert r.status_code == 200, r.get_data(as_text=True)


class TestWithdraw:
    def test_withdraw_prepared_envelope(self, pg_app, seeded):
        from app.extensions import db

        envelope, _ = _mk_envelope(pg_app, seeded)
        envelope.state = "prepared"
        envelope.prepared_at = datetime.utcnow()
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["creator"].id))
        r = client.post(
            f"/api/envelopes/{envelope.id}/withdraw",
            json={"reason": "duplicate envelope"},
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"withdraw-{envelope.id}",
            },
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        body = r.get_json()
        assert body["state"] == "withdrawn"
        assert body["withdraw_reason"] == "duplicate envelope"

    def test_withdraw_blocked_after_decision(self, pg_app, seeded):
        from app.extensions import db

        envelope, participants = _mk_envelope(pg_app, seeded)
        envelope.state = "prepared"
        envelope.prepared_at = datetime.utcnow()
        db.session.commit()
        r = _issue_and_decide(
            pg_app,
            envelope,
            participants["signer_a"],
            seeded["signer_a"],
            "routingpassword12345",
        )
        assert r.status_code == 201
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["creator"].id))
        r = client.post(
            f"/api/envelopes/{envelope.id}/withdraw",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"withdraw-blocked-{envelope.id}",
            },
        )
        assert r.status_code == 409


class TestReminderAndResend:
    def test_reminder_sends_email(self, pg_app, seeded):
        from app.extensions import db
        from app.services import email as mailer

        envelope, participants = _mk_envelope(pg_app, seeded)
        envelope.state = "prepared"
        envelope.prepared_at = datetime.utcnow()
        db.session.commit()
        mailer.clear_outbox()
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["creator"].id))
        r = client.post(
            f"/api/envelopes/{envelope.id}/participants/{participants['signer_a'].id}/reminder",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        outbox = mailer.outbox()
        assert len(outbox) == 1
        assert outbox[0].to == seeded["signer_a"].email

    def test_reminder_refused_after_decision(self, pg_app, seeded):
        from app.extensions import db

        envelope, participants = _mk_envelope(pg_app, seeded)
        envelope.state = "prepared"
        envelope.prepared_at = datetime.utcnow()
        db.session.commit()
        _issue_and_decide(
            pg_app,
            envelope,
            participants["signer_a"],
            seeded["signer_a"],
            "routingpassword12345",
        )
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["creator"].id))
        r = client.post(
            f"/api/envelopes/{envelope.id}/participants/{participants['signer_a'].id}/reminder",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 409

    def test_resend_invitation_rotates_token(self, pg_app, seeded):
        from app.extensions import db
        from app.models.signer_invitation import SignerInvitation
        from app.services import signer_invitations

        envelope, participants = _mk_envelope(pg_app, seeded)
        envelope.state = "prepared"
        envelope.prepared_at = datetime.utcnow()
        db.session.commit()
        _row, original_token = signer_invitations.issue(
            envelope=envelope,
            participant=participants["signer_a"],
            issued_by_id=seeded["creator"].id,
        )
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["creator"].id))
        r = client.post(
            f"/api/envelopes/{envelope.id}/participants/{participants['signer_a'].id}/resend-invitation",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        body = r.get_json()
        assert body["token"] != original_token
        # Original invitation is revoked.
        active = SignerInvitation.query.filter_by(
            envelope_id=envelope.id,
            participant_id=participants["signer_a"].id,
            revoked_at=None,
            consumed_at=None,
        ).count()
        assert active == 1  # the new one
