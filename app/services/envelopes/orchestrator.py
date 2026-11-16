"""Single authoritative orchestrator for envelope finalization.

The flow (one DB transaction):

    prepared envelope
        -> authorize separate-duty operator
        -> validate every participant decision + review receipt
        -> validate signer-held endorsement signatures
        -> fetch source PDF bytes from immutable storage, verify digest
        -> platform-seal the PDF with the configured signing credentials
        -> persist the sealed PDF bytes (private storage)
        -> record FinalizedPdf
        -> emit the outbox event ``platform.pdf.sealed``
        -> commit

If any step fails the transaction is rolled back. On storage failure
after seal the orphan is cleaned up by the caller.

Separation of concerns:

* This module never calls Click. It raises :class:`OrchestratorError`;
  the CLI translates to a user-facing message.
* It never calls Flask abort. HTTP endpoints must catch the exception
  and shape their own response.
* Idempotency: if a :class:`FinalizedPdf` already exists for the
  envelope, :meth:`finalize` returns a result with ``already_finalized``
  set rather than raising. Callers that need idempotency across clients
  should still wrap the endpoint in ``app.services.idempotency``.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from typing import Any

from flask import current_app

from app.extensions import db
from app.models.documents.document_blob import DocumentBlob
from app.models.pdf_finalization import FinalizedPdf
from app.models.review_receipt import ReviewReceipt
from app.models.signer_cryptographic import SignerEndorsement, SignerPublicKey
from app.models.signer_decision import SignerDecision
from app.models.signing_envelope import EnvelopeParticipant, SigningEnvelope
from app.models.user import User
from app.services.documents.private_storage import (
    IngestionError,
    check_object_digest,
    cleanup_object,
    store_scanned_pdf,
)
from app.services.event_delivery import enqueue
from app.services.platform_pdf_seal import PdfFinalizationError, seal_pdf
from app.services.platform_review_evidence import (
    canonical_evidence_bundle,
    evidence_digest,
)
from app.services.signer_crypto import endorsement_payload, verify_detached
from app.services.signing_receipts import (
    resolve_trusted_public_key,
    review_payload,
    verify_receipt,
)


class OrchestratorError(RuntimeError):
    """Domain-level failure in the finalization flow.

    Carries a short ``reason`` code so callers can branch (e.g. the CLI
    returns a user-facing message; HTTP returns a specific 4xx/5xx).
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class FinalizeResult:
    envelope_id: int
    finalized_pdf_id: int
    organization_id: int
    output_sha256: str
    evidence_sha256: str
    certificate_sha256: str
    operator_id: int
    already_finalized: bool


class EnvelopeOrchestrator:
    """Compose the envelope finalization steps.

    One instance is cheap to construct; the Flask application and SQLA
    session are pulled from the active context, matching the convention
    used by the rest of the services module.
    """

    def __init__(self, *, config: Any | None = None) -> None:
        self._config = config

    @property
    def config(self) -> Any:
        return self._config if self._config is not None else current_app.config

    # ----- public ---------------------------------------------------

    def finalize(self, envelope_id: int) -> FinalizeResult:
        """Finalize ``envelope_id`` end to end.

        Returns the existing record (``already_finalized=True``) when the
        envelope was finalized by a prior transaction. Otherwise runs the
        full flow and returns a fresh result.

        Raises :class:`OrchestratorError` with a stable ``reason`` tag on
        every refusal.
        """
        envelope = (
            db.session.query(SigningEnvelope)
            .filter_by(id=envelope_id)
            .with_for_update()
            .first()
        )
        if envelope is None:
            raise OrchestratorError("envelope_not_found", "Envelope not found")

        existing = (
            db.session.query(FinalizedPdf).filter_by(envelope_id=envelope.id).first()
        )
        if existing is not None:
            # Do not raise; idempotency mandates returning the stored outcome.
            return self._result(envelope, existing, already_finalized=True)

        if envelope.state != "prepared":
            db.session.rollback()
            raise OrchestratorError(
                "envelope_not_prepared",
                f"Envelope state is {envelope.state!r}; only 'prepared' may be sealed",
            )

        object_key: str | None = None
        try:
            operator = self._authorize_operator(envelope)
            digest = self._validate_review_bundle(envelope)
            source_bytes = self._load_source_bytes(envelope)
            signed, certificate_sha256, _status = seal_pdf(
                source_bytes, self.config, digest
            )
            object_key, _name, size, output_digest, _scanner = store_scanned_pdf(
                io.BytesIO(signed),
                f"TrustSeal-sealed-envelope-{envelope.id}.pdf",
                self.config,
            )
            record = FinalizedPdf(
                envelope_id=envelope.id,
                organization_id=envelope.organization_id,
                issued_by_id=operator.id,
                source_blob_id=envelope.document_blob_id,
                source_sha256=envelope.document_sha256,
                evidence_sha256=digest,
                object_key=object_key,
                output_sha256=output_digest,
                output_size=size,
                certificate_sha256=certificate_sha256,
                signature_field="TrustSealPlatformSeal",
                profile="platform_pades_b_b",
            )
            db.session.add(record)
            db.session.flush()
            # Phase X1 — in-app notification to the envelope owner.
            from app.services import operator_notifications

            operator_notifications.publish(
                organization_id=envelope.organization_id,
                recipient_user_id=envelope.created_by_id,
                kind="envelope.sealed",
                subject_type="signing_envelope",
                subject_id=envelope.id,
                summary=(
                    f"Envelope #{envelope.id} has been sealed. Finalized PDF "
                    f"digest: {output_digest[:16]}…"
                ),
            )
            enqueue(
                event_type="platform.pdf.sealed",
                aggregate_type="envelope",
                aggregate_id=envelope.id,
                organization_id=envelope.organization_id,
                actor_id=operator.id,
                action="platform.pdf.sealed.authorized_operator",
                idempotency_key=f"platform-pdf-sealed:{envelope.id}",
            )
            db.session.commit()
            return self._result(envelope, record, already_finalized=False)
        except OrchestratorError:
            db.session.rollback()
            if object_key:
                self._cleanup(object_key)
            raise
        except (PdfFinalizationError, IngestionError) as exc:
            db.session.rollback()
            if object_key:
                self._cleanup(object_key)
            raise OrchestratorError(
                "finalization_integrity_failed", str(exc) or type(exc).__name__
            ) from exc
        except (ValueError, OSError) as exc:
            db.session.rollback()
            if object_key:
                self._cleanup(object_key)
            raise OrchestratorError(
                "finalization_unexpected_failure", type(exc).__name__
            ) from exc

    # ----- internals ------------------------------------------------

    def _result(
        self, envelope: SigningEnvelope, record: FinalizedPdf, *, already_finalized: bool
    ) -> FinalizeResult:
        return FinalizeResult(
            envelope_id=envelope.id,
            finalized_pdf_id=record.id,
            organization_id=envelope.organization_id,
            output_sha256=record.output_sha256,
            evidence_sha256=record.evidence_sha256,
            certificate_sha256=record.certificate_sha256,
            operator_id=record.issued_by_id,
            already_finalized=already_finalized,
        )

    def _cleanup(self, object_key: str) -> None:
        try:
            cleanup_object(object_key, self.config)
        except Exception:  # pragma: no cover - diagnostic path
            current_app.logger.exception("Signed PDF orphan cleanup failed")

    def _authorize_operator(self, envelope: SigningEnvelope) -> User:
        """Require an active separate-duty operator set at deployment time."""
        from app.policies.api_access import is_admin  # local import to avoid cycle

        raw = self.config.get("PDF_SEAL_OPERATOR_ID")
        if raw is None or not str(raw).isdecimal():
            raise OrchestratorError(
                "operator_not_configured",
                "Platform seal operator identity is not configured",
            )
        operator = db.session.get(User, int(raw))
        if (
            operator is None
            or not operator.is_active
            or operator.organization_id != envelope.organization_id
            or operator.id == envelope.created_by_id
            or not is_admin(operator.id)
        ):
            raise OrchestratorError(
                "operator_unauthorized",
                "Authorized, independent seal operator required",
            )
        if (
            EnvelopeParticipant.query.filter_by(
                envelope_id=envelope.id, user_id=operator.id
            ).first()
            is not None
        ):
            raise OrchestratorError(
                "operator_is_participant",
                "A reviewing participant cannot self-seal",
            )
        return operator

    def _validate_review_bundle(self, envelope: SigningEnvelope) -> str:
        """Validate every participant decision, receipt and endorsement.

        Returns the canonical evidence digest the seal will embed. Raises
        :class:`OrchestratorError` with a specific reason on any breach.
        """
        participants = (
            EnvelopeParticipant.query.filter_by(envelope_id=envelope.id)
            .order_by(EnvelopeParticipant.signing_order)
            .all()
        )
        if not participants:
            raise OrchestratorError(
                "envelope_has_no_participants", "Envelope has no participants"
            )
        receipts_for_digest: list[dict[str, Any]] = []
        for participant in participants:
            decision = SignerDecision.query.filter_by(
                participant_id=participant.id
            ).first()
            if (
                decision is None
                or decision.envelope_id != envelope.id
                or decision.user_id != participant.user_id
                or decision.decision != "acknowledged"
                or decision.document_sha256 != envelope.document_sha256
            ):
                raise OrchestratorError(
                    "participant_decision_missing",
                    "All participants must acknowledge the exact PDF",
                )
            receipt = ReviewReceipt.query.filter_by(decision_id=decision.id).first()
            if receipt is None:
                raise OrchestratorError(
                    "review_receipt_missing",
                    "Every review must have a signed receipt",
                )
            detached = {
                "payload": receipt.payload,
                "signature": receipt.signature,
                "algorithm": receipt.algorithm,
                "key_id": receipt.key_id,
            }
            try:
                key = resolve_trusted_public_key(self.config, receipt.key_id)
            except (OSError, ValueError, TypeError) as exc:
                raise OrchestratorError(
                    "review_receipt_key_untrusted",
                    "Review receipt signing key is not trusted",
                ) from exc
            if not verify_receipt(detached, key):
                raise OrchestratorError(
                    "review_receipt_signature_invalid",
                    "Review receipt signature invalid",
                )
            if receipt.payload != review_payload(envelope, participant, decision):
                raise OrchestratorError(
                    "review_receipt_evidence_mismatch",
                    "Review receipt evidence mismatch",
                )
            endorsement = SignerEndorsement.query.filter_by(
                envelope_id=envelope.id, participant_id=participant.id
            ).first()
            if endorsement is None or endorsement.user_id != participant.user_id:
                raise OrchestratorError(
                    "signer_endorsement_missing",
                    "Missing signer-controlled document endorsement",
                )
            signer_key = db.session.get(SignerPublicKey, endorsement.signer_key_id)
            if signer_key is None or signer_key.user_id != participant.user_id:
                raise OrchestratorError(
                    "signer_key_unavailable",
                    "Signer public key record unavailable",
                )
            try:
                expected_endorsement = endorsement_payload(
                    envelope=envelope,
                    participant=participant,
                    decision=decision,
                    fingerprint=signer_key.fingerprint,
                    nonce=endorsement.signed_payload.get("nonce"),
                )
            except (ValueError, TypeError, AttributeError) as exc:
                raise OrchestratorError(
                    "signer_endorsement_context_invalid",
                    "Invalid signer endorsement context",
                ) from exc
            if endorsement.signed_payload != expected_endorsement or not verify_detached(
                signer_key.public_key_pem,
                endorsement.signed_payload,
                endorsement.signature_b64,
            ):
                raise OrchestratorError(
                    "signer_endorsement_invalid",
                    "Signer-controlled endorsement invalid",
                )
            receipts_for_digest.append(
                {
                    "signer_endorsement": {
                        "public_key_pem": signer_key.public_key_pem,
                        "key_fingerprint": signer_key.fingerprint,
                        "signed_payload": endorsement.signed_payload,
                        "signature_b64": endorsement.signature_b64,
                    },
                    "participant_id": participant.id,
                    "signing_order": participant.signing_order,
                    "review_decision_id": decision.id,
                    "payload": receipt.payload,
                    "algorithm": receipt.algorithm,
                    "key_id": receipt.key_id,
                    "signature": receipt.signature,
                }
            )
        bundle = canonical_evidence_bundle(envelope.id, receipts_for_digest)
        return evidence_digest(bundle)

    def _load_source_bytes(self, envelope: SigningEnvelope) -> bytes:
        original = db.session.get(DocumentBlob, envelope.document_blob_id)
        if (
            original is None
            or original.document_id != envelope.document_id
            or original.sha256 != envelope.document_sha256
        ):
            raise OrchestratorError(
                "frozen_source_mismatch", "Frozen source manifest mismatch"
            )
        try:
            path = check_object_digest(original.object_key, original.sha256, self.config)
        except IngestionError as exc:
            raise OrchestratorError(
                "source_storage_unavailable", "Source PDF storage integrity failed"
            ) from exc
        bytes_ = path.read_bytes()
        if hashlib.sha256(bytes_).hexdigest() != envelope.document_sha256:
            raise OrchestratorError(
                "source_digest_mismatch", "Source bytes do not match envelope"
            )
        return bytes_
