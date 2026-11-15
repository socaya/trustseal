"""Email verification tokens.

One row per outstanding verification attempt for a user's declared
email address. The raw token value only ever lives in-memory and in
the outbound email — the DB stores its SHA-256 digest. Consuming a
token stamps ``consumed_at`` and refuses future reuse.

Each row carries the ``email`` string it was issued for: if a user
changes their email between issuance and consumption, the stale token
no longer validates the new address.
"""
from datetime import datetime

from app.extensions import db


class EmailVerificationToken(db.Model):
    __tablename__ = "email_verification_tokens"

    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    email = db.Column(db.String(120), nullable=False)
    token_sha256 = db.Column(db.String(64), nullable=False, unique=True)
    issued_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    consumed_at = db.Column(db.DateTime, nullable=True)
    issued_from_ip = db.Column(db.String(45), nullable=True)

    __table_args__ = (
        db.Index(
            "ix_email_verification_tokens_user_active",
            "user_id",
            postgresql_where=db.text("consumed_at IS NULL"),
        ),
    )
