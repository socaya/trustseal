"""Signer-uploaded supporting attachments (Phase U1).

A signer reviewing an envelope may upload supporting evidence —
an ID photo, a counter-signed memo, a verification document —
alongside their acknowledgement. Attachments are:

* stored through the pluggable private-storage backend
  (``PrivateObjectStore``) so they inherit the same custody /
  RLS / scanner policy as primary document blobs;
* hashed at upload time; the SHA-256 is immutable and is
  included in the signed Ed25519 receipt so the receipt attests
  to the exact bytes the signer attached;
* bound to a single ``SignerDecision`` after decision time. Rows
  with ``decision_id IS NULL`` are "staged" — created by the
  signer but not yet linked to a decision. They are dropped
  automatically if the signer never completes the decision (the
  envelope withdraw / expire paths clean them up).

Attachments are *not* a replacement for the main signed PDF —
they are supplementary evidence, surfaced in the signing
receipt and the per-envelope evidence view.
"""
from datetime import datetime

from app.extensions import db


class SignerAttachment(db.Model):
    __tablename__ = "signer_attachments"

    id = db.Column(db.BigInteger, primary_key=True)
    envelope_id = db.Column(
        db.Integer,
        db.ForeignKey("signing_envelopes.id"),
        nullable=False,
        index=True,
    )
    participant_id = db.Column(
        db.Integer,
        db.ForeignKey("envelope_participants.id"),
        nullable=False,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    decision_id = db.Column(
        db.BigInteger,
        db.ForeignKey("signer_decisions.id"),
        nullable=True,
    )
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    object_key = db.Column(db.String(200), nullable=False, unique=True)
    file_name = db.Column(db.String(200), nullable=False)
    mime_type = db.Column(db.String(80), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    scanner = db.Column(db.String(60), nullable=False)
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        db.CheckConstraint(
            "file_size > 0 AND file_size <= 10485760",
            name="ck_signer_attachment_size",
        ),
        db.CheckConstraint(
            "mime_type IN ('application/pdf','image/png','image/jpeg')",
            name="ck_signer_attachment_mime",
        ),
        db.CheckConstraint(
            "char_length(file_name) >= 1 AND char_length(file_name) <= 200",
            name="ck_signer_attachment_name_length",
        ),
    )
