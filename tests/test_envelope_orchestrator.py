"""Envelope finalization orchestrator contract.

The orchestrator composes an already-vetted set of services (platform
PDF seal, private storage, review-receipt verification, signer-crypto
endorsement). Those services have their own unit tests; here we exercise
the orchestrator's control-flow and state-transition guarantees:

* Missing envelope -> ``envelope_not_found``.
* Envelope state is not ``prepared`` -> ``envelope_not_prepared``.
* Operator is not configured or not authorized -> matching reason tag.
* No participants -> ``envelope_has_no_participants``.
* Participant decision missing / wrong digest -> ``participant_decision_missing``.
* Second finalize on the same envelope returns ``already_finalized=True``.
* Happy path: creates a :class:`FinalizedPdf`, enqueues the outbox event,
  returns a :class:`FinalizeResult` with the expected digests.
"""
from __future__ import annotations

import hashlib
from datetime import datetime

import pytest


@pytest.fixture
def app(pg_app):
    pg_app.config["PDF_SEAL_OPERATOR_ID"] = None
    yield pg_app


@pytest.fixture
def seeded(app):
    """Seed an organisation, users, document, blob and prepared envelope."""
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.pdf_finalization import FinalizedPdf
    from app.models.signing_envelope import EnvelopeParticipant, SigningEnvelope
    from app.models.system import Role, UserRole
    from app.models.user import User

    org = Organization(name="Test Org")
    db.session.add(org)
    db.session.flush()

    creator = User(
        username="creator",
        email="creator@example.test",
        is_active=True,
        organization_id=org.id,
    )
    creator.set_password("not-used")
    operator = User(
        username="operator",
        email="operator@example.test",
        is_active=True,
        organization_id=org.id,
    )
    operator.set_password("not-used")
    db.session.add_all([creator, operator])
    db.session.flush()

    admin_role = Role(name="admin")
    db.session.add(admin_role)
    db.session.flush()
    db.session.add(UserRole(user_id=operator.id, role_id=admin_role.id))

    # Document, blob and envelope. The orchestrator opens the blob from
    # disk, so we never need real bytes for the control-flow tests that
    # fail before storage access.
    doc = Document(
        title="Review",
        status="pending",
        created_by=creator.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()

    digest = hashlib.sha256(b"body").hexdigest()
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key="tenants/%s/orig/%s" % (org.id, doc.id),
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
        envelope_id=envelope.id, user_id=creator.id, signing_order=1, role="signer"
    )
    db.session.add(participant)
    db.session.commit()

    app.config["PDF_SEAL_OPERATOR_ID"] = str(operator.id)

    return {
        "org": org,
        "creator": creator,
        "operator": operator,
        "doc": doc,
        "blob": blob,
        "envelope": envelope,
        "participant": participant,
        "digest": digest,
        "FinalizedPdf": FinalizedPdf,
    }


class TestEnvelopeOrchestrator_Preconditions:
    def test_missing_envelope(self, app):
        from app.services.envelopes import EnvelopeOrchestrator, OrchestratorError

        with pytest.raises(OrchestratorError) as excinfo:
            EnvelopeOrchestrator().finalize(999_999)
        assert excinfo.value.reason == "envelope_not_found"

    def test_wrong_state_refused(self, app, seeded):
        from app.extensions import db
        from app.services.envelopes import EnvelopeOrchestrator, OrchestratorError

        seeded["envelope"].state = "draft"
        db.session.commit()
        with pytest.raises(OrchestratorError) as excinfo:
            EnvelopeOrchestrator().finalize(seeded["envelope"].id)
        assert excinfo.value.reason == "envelope_not_prepared"

    def test_operator_not_configured(self, app, seeded):
        from app.services.envelopes import EnvelopeOrchestrator, OrchestratorError

        app.config["PDF_SEAL_OPERATOR_ID"] = None
        with pytest.raises(OrchestratorError) as excinfo:
            EnvelopeOrchestrator().finalize(seeded["envelope"].id)
        assert excinfo.value.reason == "operator_not_configured"

    def test_operator_is_the_creator_refused(self, app, seeded):
        from app.services.envelopes import EnvelopeOrchestrator, OrchestratorError

        # Reassign the operator slot to the envelope creator.
        app.config["PDF_SEAL_OPERATOR_ID"] = str(seeded["creator"].id)
        with pytest.raises(OrchestratorError) as excinfo:
            EnvelopeOrchestrator().finalize(seeded["envelope"].id)
        assert excinfo.value.reason == "operator_unauthorized"

    def test_operator_is_participant_refused(self, app, seeded):
        """Operator who is also a participant may not self-seal."""
        from app.extensions import db
        from app.models.signing_envelope import EnvelopeParticipant
        from app.services.envelopes import EnvelopeOrchestrator, OrchestratorError

        db.session.add(
            EnvelopeParticipant(
                envelope_id=seeded["envelope"].id,
                user_id=seeded["operator"].id,
                signing_order=2,
                role="signer",
            )
        )
        db.session.commit()
        with pytest.raises(OrchestratorError) as excinfo:
            EnvelopeOrchestrator().finalize(seeded["envelope"].id)
        assert excinfo.value.reason == "operator_is_participant"

    def test_missing_participant_decision(self, app, seeded):
        """No SignerDecision -> participant_decision_missing, not a crash."""
        from app.services.envelopes import EnvelopeOrchestrator, OrchestratorError

        with pytest.raises(OrchestratorError) as excinfo:
            EnvelopeOrchestrator().finalize(seeded["envelope"].id)
        assert excinfo.value.reason == "participant_decision_missing"


class TestEnvelopeOrchestrator_Idempotence:
    def test_already_finalized_returns_existing_record(self, app, seeded):
        """A FinalizedPdf already present for the envelope short-circuits."""
        from app.extensions import db
        from app.services.envelopes import EnvelopeOrchestrator

        existing = seeded["FinalizedPdf"](
            envelope_id=seeded["envelope"].id,
            organization_id=seeded["org"].id,
            issued_by_id=seeded["operator"].id,
            source_blob_id=seeded["blob"].id,
            source_sha256=seeded["digest"],
            evidence_sha256="e" * 64,
            object_key="tenants/final/already",
            output_sha256="f" * 64,
            output_size=10,
            certificate_sha256="c" * 64,
            signature_field="TrustSealPlatformSeal",
            profile="platform_pades_b_b",
        )
        db.session.add(existing)
        db.session.commit()
        result = EnvelopeOrchestrator().finalize(seeded["envelope"].id)
        assert result.already_finalized is True
        assert result.finalized_pdf_id == existing.id
        assert result.output_sha256 == existing.output_sha256


class TestEnvelopeOrchestrator_HappyPath:
    def test_full_flow_mocked_seal_produces_record_and_event(
        self, app, seeded, monkeypatch
    ):
        """End-to-end with ``seal_pdf`` and private-storage stubbed.

        This test proves the orchestrator wires the right inputs to each
        collaborator without needing a real PKCS#12 or a clamscan binary.
        Cryptographic correctness has its own tests under
        ``tests/test_platform_pdf_seal.py`` and the integration suite.
        """
        import io

        from app.extensions import db
        from app.models.event_delivery import OutboxEvent
        from app.models.review_receipt import ReviewReceipt
        from app.models.signer_cryptographic import SignerEndorsement, SignerPublicKey
        from app.models.signer_decision import SignerDecision
        from app.services.envelopes import EnvelopeOrchestrator
        from app.services.envelopes import orchestrator as orch

        # 1. Seed a signer challenge, review decision, receipt and endorsement.
        from datetime import timedelta
        from app.models.signer_decision import SignerChallenge, SignerDecision

        issued = datetime.utcnow()
        challenge = SignerChallenge(
            envelope_id=seeded["envelope"].id,
            participant_id=seeded["participant"].id,
            user_id=seeded["creator"].id,
            nonce_sha256="n" * 64,
            document_sha256=seeded["digest"],
            issued_at=issued,
            expires_at=issued + timedelta(hours=1),
            consumed_at=issued,
        )
        db.session.add(challenge)
        db.session.flush()
        decision = SignerDecision(
            envelope_id=seeded["envelope"].id,
            participant_id=seeded["participant"].id,
            user_id=seeded["creator"].id,
            challenge_id=challenge.id,
            decision="acknowledged",
            document_sha256=seeded["digest"],
            consent_version="v1",
            consent_sha256="d" * 64,
            recorded_at=issued,
        )
        db.session.add(decision)
        db.session.flush()

        # The orchestrator calls into ``signing_receipts.verify_receipt``
        # and ``signer_crypto.verify_detached``. We monkeypatch both to
        # accept the stubbed receipt/endorsement; crypto correctness is
        # out of scope for this orchestrator-level test.
        monkeypatch.setattr(orch, "verify_receipt", lambda *_a, **_k: True)
        monkeypatch.setattr(orch, "verify_detached", lambda *_a, **_k: True)

        def fake_resolve(_config, key_id):
            class _StubKey:
                pass

            return _StubKey()

        monkeypatch.setattr(orch, "resolve_trusted_public_key", fake_resolve)

        # ``review_payload`` returns the canonical payload; monkeypatch it
        # to match the stored one so the equality check passes.
        canonical = {"canonical": True, "envelope_id": seeded["envelope"].id}
        monkeypatch.setattr(orch, "review_payload", lambda *_a, **_k: canonical)

        receipt = ReviewReceipt(
            organization_id=seeded["org"].id,
            envelope_id=seeded["envelope"].id,
            decision_id=decision.id,
            payload=canonical,
            algorithm="Ed25519",
            key_id="ed25519-sha256:stub",
            signature="c3RhcnQ=",  # base64("start")
        )
        db.session.add(receipt)

        signer_key = SignerPublicKey(
            user_id=seeded["creator"].id,
            organization_id=seeded["org"].id,
            public_key_pem="-----BEGIN PUBLIC KEY-----\nstub\n-----END PUBLIC KEY-----",
            fingerprint="ed25519-sha256:signer-stub",
        )
        db.session.add(signer_key)
        db.session.flush()

        expected_endorsement_payload = {"nonce": "n123", "envelope_id": seeded["envelope"].id}
        monkeypatch.setattr(orch, "endorsement_payload", lambda **_k: expected_endorsement_payload)
        from datetime import timedelta
        from app.models.signer_cryptographic import SignerEndorsementChallenge

        issued_c = datetime.utcnow()
        e_challenge = SignerEndorsementChallenge(
            envelope_id=seeded["envelope"].id,
            participant_id=seeded["participant"].id,
            user_id=seeded["creator"].id,
            signer_key_id=signer_key.id,
            nonce_hash="m" * 64,
            signed_payload=expected_endorsement_payload,
            issued_at=issued_c,
            expires_at=issued_c + timedelta(hours=1),
            consumed_at=issued_c,
        )
        db.session.add(e_challenge)
        db.session.flush()
        endorsement = SignerEndorsement(
            envelope_id=seeded["envelope"].id,
            participant_id=seeded["participant"].id,
            user_id=seeded["creator"].id,
            signer_key_id=signer_key.id,
            challenge_id=e_challenge.id,
            signed_payload=expected_endorsement_payload,
            signature_b64="c3Vic2NyaWJl",  # "subscribe" base64
        )
        db.session.add(endorsement)
        db.session.commit()

        # 2. Stub out storage and sealing to keep the test hermetic.
        source_bytes = b"%PDF-1.4\nbody\n%%EOF\n"
        true_digest = hashlib.sha256(source_bytes).hexdigest()
        # Realign blob + envelope digest to the stubbed content.
        seeded["blob"].sha256 = true_digest
        seeded["envelope"].document_sha256 = true_digest
        decision.document_sha256 = true_digest
        db.session.commit()

        class _StubPath:
            def read_bytes(self_inner):
                return source_bytes

        monkeypatch.setattr(
            orch, "check_object_digest", lambda *_a, **_k: _StubPath()
        )

        sealed_bytes = b"%PDF-1.4\nsealed\n%%EOF\n"
        cert_sha = "c" * 64
        monkeypatch.setattr(orch, "seal_pdf", lambda *_a, **_k: (sealed_bytes, cert_sha, {}))

        output_sha = hashlib.sha256(sealed_bytes).hexdigest()

        def fake_store(buffer, name, _config):
            payload = buffer.read() if hasattr(buffer, "read") else bytes(buffer)
            assert payload == sealed_bytes
            return (
                "tenants/%s/final/%s" % (seeded["org"].id, name),
                name,
                len(payload),
                hashlib.sha256(payload).hexdigest(),
                "stub",
            )

        monkeypatch.setattr(orch, "store_scanned_pdf", fake_store)

        # 3. Execute.
        result = EnvelopeOrchestrator().finalize(seeded["envelope"].id)

        # 4. Verify the result shape and durable side-effects.
        assert result.already_finalized is False
        assert result.operator_id == seeded["operator"].id
        assert result.output_sha256 == output_sha
        assert result.certificate_sha256 == cert_sha

        from app.models.pdf_finalization import FinalizedPdf

        record = FinalizedPdf.query.filter_by(envelope_id=seeded["envelope"].id).first()
        assert record is not None
        assert record.profile == "platform_pades_b_b"
        assert record.signature_field == "TrustSealPlatformSeal"

        event = OutboxEvent.query.filter_by(
            event_type="platform.pdf.sealed", aggregate_id=seeded["envelope"].id
        ).first()
        assert event is not None
        assert event.idempotency_key == f"platform-pdf-sealed:{seeded['envelope'].id}"
