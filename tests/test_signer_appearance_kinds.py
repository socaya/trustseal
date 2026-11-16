"""Typed + uploaded signature appearances (I2 + I3).

Covers the service layer directly (the end-to-end HTTP decision path
is already covered in ``tests/test_signer_appearances.py``). These
tests exercise the new kinds' server-side rendering + normalisation.
"""
from __future__ import annotations

import io

import pytest
from PIL import Image


# ---------------------------------------------------------- I2 typed


class TestRenderTyped:
    def test_disabled_by_default(self, pg_app):
        from app.services import signer_appearances

        with pytest.raises(signer_appearances.AppearanceError):
            signer_appearances.render_typed("Jane Doe", config=pg_app.config)

    def test_renders_png(self, pg_app):
        from app.services import signer_appearances

        pg_app.config["TYPED_SIGNATURE_RENDERING_ENABLED"] = True
        png = signer_appearances.render_typed(
            "Jane Doe", config=pg_app.config
        )
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        # Decodable + has reasonable dimensions.
        with Image.open(io.BytesIO(png)) as img:
            assert img.format == "PNG"
            assert img.size[0] > 100
            assert img.size[1] > 40
        pg_app.config["TYPED_SIGNATURE_RENDERING_ENABLED"] = False

    def test_rejects_empty_name(self, pg_app):
        from app.services import signer_appearances

        pg_app.config["TYPED_SIGNATURE_RENDERING_ENABLED"] = True
        try:
            with pytest.raises(signer_appearances.AppearanceError):
                signer_appearances.render_typed("", config=pg_app.config)
            with pytest.raises(signer_appearances.AppearanceError):
                signer_appearances.render_typed("   ", config=pg_app.config)
        finally:
            pg_app.config["TYPED_SIGNATURE_RENDERING_ENABLED"] = False

    def test_rejects_control_characters(self, pg_app):
        from app.services import signer_appearances

        pg_app.config["TYPED_SIGNATURE_RENDERING_ENABLED"] = True
        try:
            with pytest.raises(signer_appearances.AppearanceError):
                signer_appearances.render_typed(
                    "Jane\nDoe", config=pg_app.config
                )
        finally:
            pg_app.config["TYPED_SIGNATURE_RENDERING_ENABLED"] = False


# ---------------------------------------------------------- I3 uploaded


def _png(size=(120, 60)) -> bytes:
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _jpeg(size=(120, 60)) -> bytes:
    img = Image.new("RGB", size, (200, 200, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


class TestNormaliseUploaded:
    def test_png_passes_through(self):
        from app.services import signer_appearances

        png = _png()
        assert signer_appearances.normalise_uploaded(png) == png

    def test_jpeg_converted_to_png(self):
        from app.services import signer_appearances

        out = signer_appearances.normalise_uploaded(_jpeg())
        assert out.startswith(b"\x89PNG\r\n\x1a\n")

    def test_rejects_other_formats(self):
        from app.services import signer_appearances

        with pytest.raises(signer_appearances.AppearanceError):
            signer_appearances.normalise_uploaded(b"GIF89a-not-supported")

    def test_rejects_oversized(self):
        from app.services import signer_appearances

        big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (
            signer_appearances.MAX_APPEARANCE_BYTES + 1
        )
        with pytest.raises(signer_appearances.AppearanceError):
            signer_appearances.normalise_uploaded(big)


# ---------------------------------------------------------- store kind


class TestStoreKind:
    def test_store_records_kind(self, pg_app, tmp_path):
        """``store`` persists the chosen ``appearance_kind``."""
        from datetime import datetime

        from app.extensions import db
        from app.models.documents.document import Document
        from app.models.documents.document_blob import DocumentBlob
        from app.models.organization import Organization
        from app.models.signer_appearance import SignerAppearance
        from app.models.signer_decision import SignerChallenge, SignerDecision
        from app.models.signing_envelope import (
            EnvelopeParticipant,
            SigningEnvelope,
        )
        from app.models.user import User
        from app.services import signer_appearances

        private_root = tmp_path / "private"
        private_root.mkdir(mode=0o700)
        pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)

        org = Organization(name="Kind Tenant", type="company")
        db.session.add(org)
        db.session.flush()
        user = User(
            username="kind-user",
            email="kind-user@example.test",
            is_active=True,
            organization_id=org.id,
        )
        user.set_password("kindpassword12345")
        db.session.add(user)
        db.session.flush()
        doc = Document(
            title="Kind doc",
            status="draft",
            created_by=user.id,
            organization_id=org.id,
        )
        db.session.add(doc)
        db.session.flush()
        blob = DocumentBlob(
            document_id=doc.id,
            revision=1,
            object_key="k" * 64 + ".pdf",
            file_name="k.pdf",
            mime_type="application/pdf",
            file_size=4,
            sha256="k" * 64,
            scanner="noop",
            created_by_id=user.id,
        )
        db.session.add(blob)
        db.session.flush()
        envelope = SigningEnvelope(
            organization_id=org.id,
            document_id=doc.id,
            document_blob_id=blob.id,
            document_sha256="k" * 64,
            created_by_id=user.id,
            state="prepared",
            prepared_at=datetime.utcnow(),
        )
        db.session.add(envelope)
        db.session.flush()
        participant = EnvelopeParticipant(
            envelope_id=envelope.id,
            user_id=user.id,
            signing_order=1,
            role="signer",
        )
        db.session.add(participant)
        db.session.flush()
        challenge = SignerChallenge(
            envelope_id=envelope.id,
            participant_id=participant.id,
            user_id=user.id,
            nonce_sha256="n" * 64,
            document_sha256="k" * 64,
            issued_at=datetime.utcnow(),
            expires_at=datetime.utcnow().replace(year=2099),
            consumed_at=datetime.utcnow(),
        )
        db.session.add(challenge)
        db.session.flush()
        decision = SignerDecision(
            envelope_id=envelope.id,
            participant_id=participant.id,
            user_id=user.id,
            challenge_id=challenge.id,
            decision="acknowledged",
            document_sha256="k" * 64,
            consent_version="review-intent-v1",
            consent_sha256="d" * 64,
            recorded_at=datetime.utcnow(),
        )
        db.session.add(decision)
        db.session.flush()

        payload = (
            "data:image/png;base64,"
            + __import__("base64").b64encode(_png()).decode()
        )
        row = signer_appearances.store(
            decision=decision,
            envelope=envelope,
            participant=participant,
            payload=payload,
            config=pg_app.config,
            appearance_kind="typed",
            source_label="Jane Doe",
        )
        db.session.commit()
        assert row.appearance_kind == "typed"
        assert row.source_label == "Jane Doe"
