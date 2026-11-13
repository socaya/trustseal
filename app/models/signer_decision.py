"""Bounded signer-intent challenge and append-only acknowledgement evidence.

Neither acknowledgement nor decline is a cryptographic PDF signature.
"""
from datetime import datetime
from app.extensions import db


class SignerChallenge(db.Model):
    __tablename__ = "signer_challenges"
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    envelope_id = db.Column(db.Integer, db.ForeignKey("signing_envelopes.id"), nullable=False, index=True)
    participant_id = db.Column(db.Integer, db.ForeignKey("envelope_participants.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    nonce_sha256 = db.Column(db.String(64), nullable=False, unique=True)
    document_sha256 = db.Column(db.String(64), nullable=False)
    issued_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    consumed_at = db.Column(db.DateTime)
    __table_args__ = (
        db.CheckConstraint("expires_at > issued_at", name="ck_signer_challenge_expiry"),
    )


class SignerDecision(db.Model):
    __tablename__ = "signer_decisions"
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    envelope_id = db.Column(db.Integer, db.ForeignKey("signing_envelopes.id"), nullable=False, index=True)
    participant_id = db.Column(db.Integer, db.ForeignKey("envelope_participants.id"), nullable=False, unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    challenge_id = db.Column(db.BigInteger, db.ForeignKey("signer_challenges.id"), nullable=False, unique=True)
    decision = db.Column(db.String(24), nullable=False)
    document_sha256 = db.Column(db.String(64), nullable=False)
    consent_version = db.Column(db.String(32), nullable=False)
    consent_sha256 = db.Column(db.String(64), nullable=False)
    recorded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        db.CheckConstraint("decision IN ('acknowledged','declined')", name="ck_signer_decision_value"),
    )
