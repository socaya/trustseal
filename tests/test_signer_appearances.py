"""Drawn signature appearance capture (second half of G10).

Service layer:

* ``decode`` accepts a ``data:image/png;base64,...`` URL and raw
  PNG bytes; rejects anything else (wrong MIME, non-PNG magic,
  oversized, empty, base64 garbage).
* ``store`` writes the PNG under PRIVATE_DOCUMENT_ROOT/signer-
  appearances/ with the file mode 0400, persists a
  :class:`SignerAppearance` row bound to the decision, and records
  the SHA-256 + size.
* ``store`` refuses when the decision and envelope / participant
  disagree.

View layer:

* The /sign review page carries a #signature-pad canvas, a hidden
  ``appearance_png_data_url`` input, and loads the vendored
  SignaturePad glue.
* Acknowledge with a valid drawn signature persists a SignerAppearance
  row and renders the recorded page.
* Acknowledge with no drawn signature still succeeds (field is
  optional).
* Acknowledge with a malformed payload redirects back with a flash
  message and leaves no appearance row behind.
"""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime
from pathlib import Path

import pytest

MIN_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


@pytest.fixture
def seeded(pg_app, tmp_path):
    """Seed an envelope + participant + invitation; no decision yet.

    The service tests mint their own decision on demand so the view
    tests (which create a decision through the HTTP flow) stay clean.
    """
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

    org = Organization(name="Appearance Tenant")
    db.session.add(org)
    db.session.flush()
    creator = User(
        username="appearance-creator",
        email="appearance-creator@example.test",
        is_active=True,
        organization_id=org.id,
    )
    creator.set_password("not-used-strong-password")
    signer = User(
        username="appearance-signer",
        email="appearance-signer@example.test",
        is_active=True,
        organization_id=org.id,
    )
    signer.set_password("not-used-strong-password")
    db.session.add_all([creator, signer])
    db.session.flush()
    doc = Document(
        title="Appearance doc",
        status="pending",
        created_by=creator.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key=f"tenants/{org.id}/orig/appearance",
        file_name="probe.pdf",
        mime_type="application/pdf",
        file_size=4,
        sha256="a" * 64,
        scanner="noop",
        created_by_id=creator.id,
    )
    db.session.add(blob)
    db.session.flush()
    envelope = SigningEnvelope(
        organization_id=org.id,
        document_id=doc.id,
        document_blob_id=blob.id,
        document_sha256="a" * 64,
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
    db.session.flush()
    _row, token = signer_invitations.issue(
        envelope=envelope,
        participant=participant,
        issued_by_id=creator.id,
    )
    db.session.commit()
    return {
        "org": org,
        "creator": creator,
        "signer": signer,
        "envelope": envelope,
        "participant": participant,
        "token": token,
        "private_root": private_root,
    }


def _mint_decision(seeded, pg_app):
    """Helper the service tests call to create a decision row to attach."""
    from app.extensions import db
    from app.models.signer_decision import SignerChallenge, SignerDecision

    challenge = SignerChallenge(
        envelope_id=seeded["envelope"].id,
        participant_id=seeded["participant"].id,
        user_id=seeded["signer"].id,
        nonce_sha256="n" * 64,
        document_sha256=seeded["envelope"].document_sha256,
        issued_at=datetime.utcnow(),
        expires_at=datetime.utcnow().replace(year=2099),
        consumed_at=datetime.utcnow(),
    )
    db.session.add(challenge)
    db.session.flush()
    decision = SignerDecision(
        envelope_id=seeded["envelope"].id,
        participant_id=seeded["participant"].id,
        user_id=seeded["signer"].id,
        challenge_id=challenge.id,
        decision="acknowledged",
        document_sha256=seeded["envelope"].document_sha256,
        consent_version="trustseal-review-consent-v1",
        consent_sha256="d" * 64,
        recorded_at=datetime.utcnow(),
    )
    db.session.add(decision)
    db.session.commit()
    return decision


def _reset_rate_limiter():
    from app.extensions import db
    from app.models.rate_limit_bucket import RateLimitBucket
    from app.services import rate_limiting

    rate_limiting.clear_cache()
    db.session.query(RateLimitBucket).delete()
    db.session.commit()


class TestDecode:
    def test_accepts_png_data_url(self):
        from app.services.signer_appearances import decode

        out = decode(_data_url(MIN_PNG))
        assert out == MIN_PNG

    def test_rejects_non_png_data_url(self):
        from app.services.signer_appearances import AppearanceError, decode

        with pytest.raises(AppearanceError):
            decode("data:image/jpeg;base64,abc")

    def test_rejects_base64_garbage(self):
        from app.services.signer_appearances import AppearanceError, decode

        with pytest.raises(AppearanceError):
            decode("data:image/png;base64,====")

    def test_rejects_empty(self):
        from app.services.signer_appearances import AppearanceError, decode

        with pytest.raises(AppearanceError):
            decode(_data_url(b""))

    def test_rejects_wrong_magic(self):
        from app.services.signer_appearances import AppearanceError, decode

        with pytest.raises(AppearanceError):
            decode(_data_url(b"GIF89a-not-a-png"))

    def test_rejects_oversized(self):
        from app.services.signer_appearances import (
            MAX_APPEARANCE_BYTES,
            AppearanceError,
            decode,
        )

        huge = MIN_PNG + (b"\x00" * (MAX_APPEARANCE_BYTES + 1))
        with pytest.raises(AppearanceError):
            decode(_data_url(huge))


class TestStore:
    def test_stores_png_and_persists_row(self, pg_app, seeded):
        from app.models.signer_appearance import SignerAppearance
        from app.services import signer_appearances

        decision = _mint_decision(seeded, pg_app)
        row = signer_appearances.store(
            decision=decision,
            envelope=seeded["envelope"],
            participant=seeded["participant"],
            payload=_data_url(MIN_PNG),
            config=pg_app.config,
        )
        assert row.sha256 == hashlib.sha256(MIN_PNG).hexdigest()
        assert row.size_bytes == len(MIN_PNG)
        stored_path = (
            Path(pg_app.config["PRIVATE_DOCUMENT_ROOT"])
            / "signer-appearances"
            / f"{row.sha256}.png"
        )
        assert stored_path.is_file()
        assert stored_path.read_bytes() == MIN_PNG
        count = SignerAppearance.query.filter_by(
            decision_id=decision.id
        ).count()
        assert count == 1

    def test_refuses_decision_envelope_mismatch(self, pg_app, seeded):
        """A decision pointing at a different envelope cannot store an appearance."""
        from app.services import signer_appearances

        decision = _mint_decision(seeded, pg_app)
        # Simulate mismatch at call time: service checks
        # ``decision.envelope_id != envelope.id``; we pass an envelope
        # whose id differs from the decision's.
        class _FakeEnvelope:
            id = seeded["envelope"].id + 1

        with pytest.raises(signer_appearances.AppearanceError) as exc:
            signer_appearances.store(
                decision=decision,
                envelope=_FakeEnvelope(),
                participant=seeded["participant"],
                payload=_data_url(MIN_PNG),
                config=pg_app.config,
            )
        assert "decision_envelope_mismatch" in str(exc.value)


class TestReviewTemplate:
    def test_page_carries_signature_pad_markup(self, pg_app, seeded):
        _reset_rate_limiter()
        r = pg_app.test_client().get(f"/sign/{seeded['token']}")
        assert r.status_code == 200
        body = r.data.decode("utf-8")
        assert 'id="signature-pad"' in body
        assert 'id="signature-clear"' in body
        assert 'name="appearance_png_data_url"' in body
        assert "/static/vendor/signature_pad/signature_pad.umd.min.js" in body
        assert "/static/vendor/signature_pad/trustseal-signature.mjs" in body


class TestDecisionFlow:
    def test_acknowledge_with_drawn_signature_persists_appearance(
        self, pg_app, seeded
    ):
        _reset_rate_limiter()
        from app.extensions import db
        from app.models.signer_appearance import SignerAppearance

        payload = _data_url(MIN_PNG)
        r = pg_app.test_client().post(
            f"/sign/{seeded['token']}/decision",
            data={
                "choice": "acknowledged",
                "appearance_png_data_url": payload,
            },
        )
        assert r.status_code == 200
        assert b"Acknowledged" in r.data
        assert b"Recorded" in r.data
        db.session.expire_all()
        appearance = SignerAppearance.query.filter_by(
            envelope_id=seeded["envelope"].id
        ).first()
        assert appearance is not None
        assert appearance.sha256 == hashlib.sha256(MIN_PNG).hexdigest()

    def test_acknowledge_without_drawn_signature_still_succeeds(
        self, pg_app, seeded
    ):
        _reset_rate_limiter()
        from app.extensions import db
        from app.models.signer_appearance import SignerAppearance

        r = pg_app.test_client().post(
            f"/sign/{seeded['token']}/decision",
            data={"choice": "acknowledged"},
        )
        assert r.status_code == 200
        db.session.expire_all()
        assert (
            SignerAppearance.query.filter_by(
                envelope_id=seeded["envelope"].id
            ).count()
            == 0
        )

    def test_malformed_signature_rejects_decision(self, pg_app, seeded):
        _reset_rate_limiter()
        from app.extensions import db
        from app.models.signer_appearance import SignerAppearance
        from app.models.signer_decision import SignerDecision

        existing_count = SignerDecision.query.filter_by(
            envelope_id=seeded["envelope"].id
        ).count()
        r = pg_app.test_client().post(
            f"/sign/{seeded['token']}/decision",
            data={
                "choice": "acknowledged",
                "appearance_png_data_url": "data:image/jpeg;base64,notpng",
            },
            follow_redirects=False,
        )
        assert r.status_code in {302, 303}
        db.session.expire_all()
        assert (
            SignerAppearance.query.filter_by(
                envelope_id=seeded["envelope"].id
            ).count()
            == 0
        )
        # The decision row count is unchanged — rollback took it out.
        assert (
            SignerDecision.query.filter_by(
                envelope_id=seeded["envelope"].id
            ).count()
            == existing_count
        )
