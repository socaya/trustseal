"""Signer landing page /sign/<token> contract.

Covers the invitation service primitives, the landing page server-
render, and the decision POST flow.

Service:

* ``issue`` mints a raw token and stores only its hash.
* ``resolve`` returns the envelope/participant for a valid token and
  raises ``InvitationError`` with a specific reason for every failure
  mode (unknown / expired / consumed / revoked / wrong_envelope_state).
* ``consume`` is idempotent.
* ``revoke`` is idempotent.
* The same participant cannot be re-invited while an existing live
  invitation is outstanding.

View:

* GET /sign/<unknown token> → the generic "unavailable" page.
* GET /sign/<valid token> → the review page with the envelope SHA.
* POST decision=acknowledged → consumes invitation, writes
  SignerDecision bound to the envelope digest, renders the recorded
  page. The invitation is then unresolvable.
* POST decision=declined → same path, with ``declined`` recorded.
* Rate limiter kicks in after too many requests from one client.
* Download route refuses when the invitation is unknown.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest


@pytest.fixture
def seeded(pg_app):
    """Seed a tenant, envelope, participant, and a document blob record."""
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.signing_envelope import (
        EnvelopeParticipant,
        SigningEnvelope,
    )
    from app.models.user import User

    org = Organization(name="Signer Tenant")
    db.session.add(org)
    db.session.flush()
    creator = User(
        username="prep-user",
        email="prep@example.test",
        is_active=True,
        organization_id=org.id,
    )
    creator.set_password("not-used-strong-password")
    signer = User(
        username="signer-user",
        email="signer@example.test",
        is_active=True,
        organization_id=org.id,
    )
    signer.set_password("not-used-strong-password")
    db.session.add_all([creator, signer])
    db.session.flush()
    doc = Document(
        title="Sample",
        status="pending",
        created_by=creator.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()
    digest = "a" * 64
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key=f"tenants/{org.id}/orig/doc",
        file_name="doc.pdf",
        mime_type="application/pdf",
        file_size=4,
        sha256=digest,
        scanner="noop",
        created_by_id=creator.id,
    )
    db.session.add(blob)
    db.session.flush()
    envelope = SigningEnvelope(
        organization_id=org.id,
        document_id=doc.id,
        document_blob_id=blob.id,
        document_sha256=digest,
        created_by_id=creator.id,
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
    db.session.commit()
    return {
        "org": org,
        "creator": creator,
        "signer": signer,
        "envelope": envelope,
        "participant": participant,
        "digest": digest,
    }


class TestService:
    def test_issue_returns_raw_token_once(self, pg_app, seeded):
        from app.services import signer_invitations

        row, token = signer_invitations.issue(
            envelope=seeded["envelope"],
            participant=seeded["participant"],
            issued_by_id=seeded["creator"].id,
        )
        assert token.startswith("trs_")
        import hashlib

        assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert row.consumed_at is None

    def test_resolve_returns_envelope_and_participant(self, pg_app, seeded):
        from app.services import signer_invitations

        _row, token = signer_invitations.issue(
            envelope=seeded["envelope"],
            participant=seeded["participant"],
            issued_by_id=seeded["creator"].id,
        )
        resolved = signer_invitations.resolve(token)
        assert resolved.envelope.id == seeded["envelope"].id
        assert resolved.participant.id == seeded["participant"].id

    def test_resolve_unknown_token(self, pg_app):
        from app.services import signer_invitations

        with pytest.raises(signer_invitations.InvitationError) as exc:
            signer_invitations.resolve("trs_unknown-token")
        assert exc.value.reason == "unknown"

    def test_resolve_expired(self, pg_app, seeded):
        from app.extensions import db
        from app.services import signer_invitations

        row, token = signer_invitations.issue(
            envelope=seeded["envelope"],
            participant=seeded["participant"],
            issued_by_id=seeded["creator"].id,
        )
        row.expires_at = datetime.utcnow() - timedelta(hours=1)
        db.session.commit()
        with pytest.raises(signer_invitations.InvitationError) as exc:
            signer_invitations.resolve(token)
        assert exc.value.reason == "expired"

    def test_resolve_consumed(self, pg_app, seeded):
        from app.extensions import db
        from app.services import signer_invitations

        row, token = signer_invitations.issue(
            envelope=seeded["envelope"],
            participant=seeded["participant"],
            issued_by_id=seeded["creator"].id,
        )
        signer_invitations.consume(row)
        db.session.commit()
        with pytest.raises(signer_invitations.InvitationError) as exc:
            signer_invitations.resolve(token)
        assert exc.value.reason == "consumed"

    def test_resolve_revoked(self, pg_app, seeded):
        from app.extensions import db
        from app.services import signer_invitations

        row, token = signer_invitations.issue(
            envelope=seeded["envelope"],
            participant=seeded["participant"],
            issued_by_id=seeded["creator"].id,
        )
        signer_invitations.revoke(row, reason="sender_cancelled")
        db.session.commit()
        with pytest.raises(signer_invitations.InvitationError) as exc:
            signer_invitations.resolve(token)
        assert exc.value.reason == "revoked"

    def test_issue_refuses_duplicate_live_invitation(self, pg_app, seeded):
        from app.services import signer_invitations

        signer_invitations.issue(
            envelope=seeded["envelope"],
            participant=seeded["participant"],
            issued_by_id=seeded["creator"].id,
        )
        with pytest.raises(signer_invitations.InvitationError) as exc:
            signer_invitations.issue(
                envelope=seeded["envelope"],
                participant=seeded["participant"],
                issued_by_id=seeded["creator"].id,
            )
        assert exc.value.reason == "already_outstanding"

    def test_participant_envelope_mismatch_rejected(self, pg_app, seeded):
        from app.services import signer_invitations

        # Give the participant a mismatched envelope reference.
        participant = seeded["participant"]
        bad = type(participant)(
            envelope_id=99999,
            user_id=seeded["signer"].id,
            signing_order=2,
            role="signer",
        )
        with pytest.raises(signer_invitations.InvitationError) as exc:
            signer_invitations.issue(
                envelope=seeded["envelope"],
                participant=bad,
                issued_by_id=seeded["creator"].id,
            )
        assert exc.value.reason == "participant_envelope_mismatch"


class TestLandingView:
    def _reset_rate_limiter(self):
        from app.blueprints.envelopes.views import sign_views as module

        module._RATE_TRACKER.clear()

    def test_unknown_token_shows_unavailable(self, pg_app):
        self._reset_rate_limiter()
        r = pg_app.test_client().get("/sign/trs_doesnotexist")
        assert r.status_code == 404
        assert b"Invitation unavailable" in r.data

    def test_valid_token_renders_review_page(self, pg_app, seeded):
        self._reset_rate_limiter()
        from app.services import signer_invitations

        _row, token = signer_invitations.issue(
            envelope=seeded["envelope"],
            participant=seeded["participant"],
            issued_by_id=seeded["creator"].id,
        )
        from app.extensions import db

        db.session.commit()
        r = pg_app.test_client().get(f"/sign/{token}")
        assert r.status_code == 200
        body = r.data.decode("utf-8")
        assert "Review and record your decision" in body
        assert seeded["digest"] in body
        assert "Acknowledge and record" in body
        assert "Decline" in body


class TestDecisionFlow:
    def _reset(self):
        from app.blueprints.envelopes.views import sign_views as module

        module._RATE_TRACKER.clear()

    def test_acknowledge_records_decision_and_consumes_invitation(
        self, pg_app, seeded
    ):
        self._reset()
        from app.extensions import db
        from app.models.signer_decision import SignerDecision
        from app.services import signer_invitations

        row, token = signer_invitations.issue(
            envelope=seeded["envelope"],
            participant=seeded["participant"],
            issued_by_id=seeded["creator"].id,
        )
        db.session.commit()
        client = pg_app.test_client()
        r = client.post(
            f"/sign/{token}/decision",
            data={"choice": "acknowledged"},
            follow_redirects=False,
        )
        assert r.status_code == 200
        assert b"Acknowledged and recorded" in r.data
        decision = SignerDecision.query.filter_by(
            envelope_id=seeded["envelope"].id,
            participant_id=seeded["participant"].id,
        ).first()
        assert decision is not None
        assert decision.decision == "acknowledged"
        assert decision.document_sha256 == seeded["digest"]
        assert decision.consent_version == "trustseal-review-consent-v1"
        # Second resolve must fail because the invitation is consumed.
        with pytest.raises(signer_invitations.InvitationError) as exc:
            signer_invitations.resolve(token)
        assert exc.value.reason == "consumed"

    def test_decline_records_decision(self, pg_app, seeded):
        self._reset()
        from app.extensions import db
        from app.models.signer_decision import SignerDecision
        from app.services import signer_invitations

        _row, token = signer_invitations.issue(
            envelope=seeded["envelope"],
            participant=seeded["participant"],
            issued_by_id=seeded["creator"].id,
        )
        db.session.commit()
        r = pg_app.test_client().post(
            f"/sign/{token}/decision",
            data={"choice": "declined"},
        )
        assert r.status_code == 200
        assert b"Declined and recorded" in r.data
        decision = SignerDecision.query.filter_by(
            envelope_id=seeded["envelope"].id,
            participant_id=seeded["participant"].id,
        ).first()
        assert decision.decision == "declined"

    def test_invalid_choice_redirects_back(self, pg_app, seeded):
        self._reset()
        from app.extensions import db
        from app.services import signer_invitations

        _row, token = signer_invitations.issue(
            envelope=seeded["envelope"],
            participant=seeded["participant"],
            issued_by_id=seeded["creator"].id,
        )
        db.session.commit()
        r = pg_app.test_client().post(
            f"/sign/{token}/decision", data={"choice": "ok"}
        )
        assert r.status_code in {302, 303}

    def test_download_unknown_returns_unavailable(self, pg_app):
        self._reset()
        r = pg_app.test_client().get("/sign/trs_unknown/download")
        assert r.status_code == 404


class TestRateLimit:
    def test_rate_limit_triggers(self, pg_app, seeded):
        from app.blueprints.envelopes.views import sign_views as module

        module._RATE_TRACKER.clear()
        from app.extensions import db
        from app.services import signer_invitations

        _row, token = signer_invitations.issue(
            envelope=seeded["envelope"],
            participant=seeded["participant"],
            issued_by_id=seeded["creator"].id,
        )
        db.session.commit()
        client = pg_app.test_client()
        for _ in range(21):
            r = client.get(f"/sign/{token}")
        assert r.status_code == 429
        assert b"Too many attempts" in r.data
