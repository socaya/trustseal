"""Signer-controlled Ed25519 key proof and detached document endorsement.

No private key is uploaded or generated server-side. Registered public keys
are proof-of-possession keys, not automatically trusted identity certificates.
"""
from datetime import datetime
from app.extensions import db


class SignerPublicKey(db.Model):
    __tablename__ = "signer_public_keys"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    fingerprint = db.Column(db.String(64), nullable=False, unique=True)
    public_key_pem = db.Column(db.Text, nullable=False)
    activated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    revoked_at = db.Column(db.DateTime)
    __table_args__ = (
        db.CheckConstraint("revoked_at IS NULL OR revoked_at >= activated_at", name="ck_signer_key_revocation_time"),
    )


class SignerKeyChallenge(db.Model):
    __tablename__ = "signer_key_challenges"
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    fingerprint = db.Column(db.String(64), nullable=False)
    public_key_pem = db.Column(db.Text, nullable=False)
    nonce_hash = db.Column(db.String(64), nullable=False, unique=True)
    issued_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    consumed_at = db.Column(db.DateTime)


class SignerEndorsementChallenge(db.Model):
    __tablename__ = "signer_endorsement_challenges"
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    envelope_id = db.Column(db.Integer, db.ForeignKey("signing_envelopes.id"), nullable=False)
    participant_id = db.Column(db.Integer, db.ForeignKey("envelope_participants.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    signer_key_id = db.Column(db.Integer, db.ForeignKey("signer_public_keys.id"), nullable=False)
    nonce_hash = db.Column(db.String(64), nullable=False, unique=True)
    signed_payload = db.Column(db.JSON, nullable=False)
    issued_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    consumed_at = db.Column(db.DateTime)


class SignerEndorsement(db.Model):
    __tablename__ = "signer_endorsements"
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    envelope_id = db.Column(db.Integer, db.ForeignKey("signing_envelopes.id"), nullable=False, index=True)
    participant_id = db.Column(db.Integer, db.ForeignKey("envelope_participants.id"), nullable=False, unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    signer_key_id = db.Column(db.Integer, db.ForeignKey("signer_public_keys.id"), nullable=False)
    challenge_id = db.Column(db.BigInteger, db.ForeignKey("signer_endorsement_challenges.id"), nullable=False, unique=True)
    signed_payload = db.Column(db.JSON, nullable=False)
    signature_b64 = db.Column(db.Text, nullable=False)
    signed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
