"""Password reset tokens.

One row per outstanding reset attempt. Like email verification, the
raw token lives only in the email body — the DB stores the SHA-256
digest. A reset is single-shot: ``consumed_at`` prevents reuse.

The ``issued_from_ip`` column exists so security-operations can
investigate suspicious patterns without having to correlate separate
request logs.
"""
from datetime import datetime

from app.extensions import db


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    token_sha256 = db.Column(db.String(64), nullable=False, unique=True)
    issued_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    consumed_at = db.Column(db.DateTime, nullable=True)
    issued_from_ip = db.Column(db.String(45), nullable=True)

    __table_args__ = (
        db.Index(
            "ix_password_reset_tokens_user_active",
            "user_id",
            postgresql_where=db.text("consumed_at IS NULL"),
        ),
    )
