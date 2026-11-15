"""Optional drawn signature appearance a signer captures on /sign.

An appearance is a small PNG rendered client-side and uploaded with
the review decision. It records *what the signer saw themselves draw*
— it is NOT a cryptographic signature. The orchestrator can later
embed the appearance in the sealed PDF as a visual element bound to
the signer's decision.

Each row carries:

* the PNG's SHA-256 (so tampering is detectable),
* its byte size,
* its stable object key in private storage,
* the decision id it belongs to (unique — one appearance per decision),
* the ingesting participant for audit attribution.
"""
from datetime import datetime

from app.extensions import db


class SignerAppearance(db.Model):
    __tablename__ = "signer_appearances"

    id = db.Column(db.BigInteger, primary_key=True)
    decision_id = db.Column(
        db.BigInteger,
        db.ForeignKey("signer_decisions.id"),
        nullable=False,
        unique=True,
    )
    envelope_id = db.Column(
        db.Integer, db.ForeignKey("signing_envelopes.id"), nullable=False
    )
    participant_id = db.Column(
        db.Integer, db.ForeignKey("envelope_participants.id"), nullable=False
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False)
    object_key = db.Column(db.String(96), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.CheckConstraint("size_bytes > 0", name="ck_signer_appearance_size"),
        db.CheckConstraint(
            "size_bytes <= 262144", name="ck_signer_appearance_size_cap"
        ),
    )
