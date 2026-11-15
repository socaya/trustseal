"""Multi-factor authentication credentials.

Each user has at most one TOTP credential at a time. Recovery codes are
one-shot — once consumed, their row is soft-deleted. Both the TOTP
secret and recovery codes are stored hashed at rest; the clear-text
secret is returned to the client exactly once during enrollment.
"""
from datetime import datetime

from app.extensions import db


class MfaCredential(db.Model):
    __tablename__ = "mfa_credentials"

    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True
    )
    secret_cipher = db.Column(db.String(512), nullable=False)
    activated_at = db.Column(db.DateTime)
    disabled_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    last_used_at = db.Column(db.DateTime)
    last_counter = db.Column(db.Integer, nullable=False, default=0)


class MfaRecoveryCode(db.Model):
    __tablename__ = "mfa_recovery_codes"

    id = db.Column(db.BigInteger, primary_key=True)
    credential_id = db.Column(
        db.BigInteger,
        db.ForeignKey("mfa_credentials.id"),
        nullable=False,
        index=True,
    )
    code_hash = db.Column(db.String(128), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    consumed_at = db.Column(db.DateTime)
