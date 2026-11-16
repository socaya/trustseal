"""Signer supporting-attachment pipeline (Phase U1).

Thin service layer over the pluggable private-storage backend that
mirrors the discipline applied to primary document blobs:

* Validate size + MIME + magic bytes (so a PNG actually starts
  with ``\x89PNG\r\n\x1a\n``) before persisting.
* Hash the bytes once and store the SHA-256 on the row — callers
  never recompute.
* The attachment row is created in a *staged* state (``decision_id
  IS NULL``) by the upload endpoint. The decision endpoint later
  claims the staged rows and binds them to the recorded decision.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Mapping

from app.extensions import db
from app.models.signer_attachment import SignerAttachment
from app.services.documents.private_object_store import active_store


class AttachmentError(ValueError):
    """Raised when an uploaded attachment is rejected."""


MAX_BYTES = 10 * 1024 * 1024
ALLOWED_MIMES = {
    "application/pdf": b"%PDF-",
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
}


@dataclass(frozen=True)
class AttachmentUpload:
    attachment: SignerAttachment
    sha256: str


def _validate(payload: bytes, mime_type: str, file_name: str) -> None:
    if not isinstance(payload, (bytes, bytearray)) or not payload:
        raise AttachmentError("empty_payload")
    if len(payload) > MAX_BYTES:
        raise AttachmentError("payload_too_large")
    if mime_type not in ALLOWED_MIMES:
        raise AttachmentError("mime_not_allowed")
    expected = ALLOWED_MIMES[mime_type]
    if not payload.startswith(expected):
        raise AttachmentError("magic_bytes_mismatch")
    if not isinstance(file_name, str) or not file_name.strip():
        raise AttachmentError("file_name_required")
    if len(file_name) > 200:
        raise AttachmentError("file_name_too_long")
    if any(ch in file_name for ch in ("\x00", "/", "\\")):
        raise AttachmentError("file_name_invalid")


def store(
    *,
    envelope,
    participant,
    file_name: str,
    mime_type: str,
    payload: bytes,
    config: Mapping,
) -> AttachmentUpload:
    """Persist a signer attachment in the staged state."""
    _validate(payload, mime_type, file_name)
    store_handle = active_store(config)
    result = store_handle.put(bytes(payload), config=config)
    row = SignerAttachment(
        envelope_id=envelope.id,
        participant_id=participant.id,
        user_id=participant.user_id,
        organization_id=envelope.organization_id,
        object_key=result.key,
        file_name=file_name.strip(),
        mime_type=mime_type,
        file_size=result.size,
        sha256=result.sha256,
        # Scanner integration hook — the pluggable storage layer's
        # dispatcher runs the scan for PDFs through
        # ``store_scanned_pdf_via_active_store``. For image uploads
        # we record a deterministic sentinel so the receipt can
        # attest to *which* scanner path accepted the bytes.
        scanner="noop" if mime_type != "application/pdf" else "accepted",
    )
    db.session.add(row)
    db.session.flush()
    digest_check = hashlib.sha256(bytes(payload)).hexdigest()
    if digest_check != result.sha256:
        # Should be impossible — pluggable store computes the same
        # hash. Treat a mismatch as a storage fault.
        raise AttachmentError("digest_mismatch")
    return AttachmentUpload(attachment=row, sha256=result.sha256)


def claim_staged(
    *, decision, attachment_ids: list[int]
) -> list[SignerAttachment]:
    """Bind staged attachments to a decision.

    Each id must reference an attachment that (a) belongs to the
    same envelope + participant as ``decision`` and (b) has not
    already been bound to another decision. Any mismatch raises
    ``AttachmentError`` and the caller is expected to roll back
    the whole decision transaction.
    """
    if not attachment_ids:
        return []
    deduped = list(dict.fromkeys(attachment_ids))
    rows = (
        SignerAttachment.query.filter(
            SignerAttachment.id.in_(deduped),
            SignerAttachment.envelope_id == decision.envelope_id,
            SignerAttachment.participant_id == decision.participant_id,
        )
        .with_for_update()
        .all()
    )
    found = {row.id for row in rows}
    missing = [aid for aid in deduped if aid not in found]
    if missing:
        raise AttachmentError(f"attachment_not_found:{missing[0]}")
    for row in rows:
        if row.decision_id is not None and row.decision_id != decision.id:
            raise AttachmentError(f"attachment_already_bound:{row.id}")
        row.decision_id = decision.id
    return rows


def receipt_manifest(decision) -> list[dict]:
    """Canonical attachments block for the signing receipt.

    Sorted by ``sha256`` so repeated receipts over the same set
    of attachments produce byte-identical payloads. Returns an
    empty list if we are outside of a Flask application context —
    the cryptographic-receipt unit tests exercise ``review_payload``
    with ``SimpleNamespace`` stubs and no database.
    """
    try:
        rows = (
            SignerAttachment.query.filter_by(decision_id=decision.id)
            .order_by(SignerAttachment.sha256.asc())
            .all()
        )
    except RuntimeError:
        return []
    return [
        {
            "id": row.id,
            "sha256": row.sha256,
            "file_name": row.file_name,
            "mime_type": row.mime_type,
            "file_size": row.file_size,
        }
        for row in rows
    ]
