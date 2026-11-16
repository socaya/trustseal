"""Hashed, time-bound invitations that bind a signer to a specific envelope.

An invitation is minted when an envelope is prepared. The caller
receives a raw token exactly once (delivered via the envelope's
recipient channel — email, SMS, in-product notification). The database
stores only its SHA-256 digest, so a compromise of the row cannot be
used to impersonate the signer.

Each invitation is:

* bound to one envelope + one participant (unique (envelope_id,
  participant_id)),
* expiring (``expires_at``),
* single-use (``consumed_at``),
* revocable (``revoked_at`` with a short reason).
"""
from datetime import datetime

from app.extensions import db


class SignerInvitation(db.Model):
    __tablename__ = "signer_invitations"

    id = db.Column(db.BigInteger, primary_key=True)
    envelope_id = db.Column(
        db.Integer, db.ForeignKey("signing_envelopes.id"), nullable=False, index=True
    )
    participant_id = db.Column(
        db.Integer,
        db.ForeignKey("envelope_participants.id"),
        nullable=False,
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    issued_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    consumed_at = db.Column(db.DateTime)
    revoked_at = db.Column(db.DateTime)
    revoke_reason = db.Column(db.String(80))
    # Last automatic reminder sent (Phase N2). The scanner uses this
    # to avoid spamming a participant every time it runs — only one
    # reminder per invitation inside the configured cooloff window.
    last_reminder_at = db.Column(db.DateTime)

    __table_args__ = (
        # Only one *active* invitation per participant at a time, but
        # history (revoked + consumed rows) persists so resend/withdraw
        # flows keep an audit trail.
        db.Index(
            "uq_signer_invitation_participant_active",
            "envelope_id",
            "participant_id",
            unique=True,
            postgresql_where=db.text(
                "revoked_at IS NULL AND consumed_at IS NULL"
            ),
        ),
    )
