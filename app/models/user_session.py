"""User sessions and device management.

Each row represents one active login (one refresh-token family). The
``family_id`` ties the session to the underlying refresh-token
lifecycle so revoking a session revokes the family and vice versa.

Tracked per-session metadata:

* ``user_agent`` and ``ip_address`` so a user can tell a phone session
  apart from a laptop session.
* ``created_at`` (login time) and ``last_seen_at`` (most recent token
  rotation or authenticated request). The UI shows both.
* ``revoked_at`` plus ``revoke_reason`` so the audit log explains why
  a session ended (user-initiated, password-change, password-reset,
  refresh-reuse detected, admin revocation).

The row carries only metadata; the actual authentication state lives
in the refresh-token family and the revoked-JTI table. Reading this
table never grants access.
"""
from datetime import datetime

from app.extensions import db


class UserSession(db.Model):
    __tablename__ = "user_sessions"

    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    family_id = db.Column(
        db.BigInteger,
        db.ForeignKey("refresh_token_families.id"),
        nullable=False,
        unique=True,
    )
    user_agent = db.Column(db.String(255), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    device_label = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    revoked_at = db.Column(db.DateTime, nullable=True)
    revoke_reason = db.Column(db.String(60), nullable=True)

    __table_args__ = (
        db.Index(
            "ix_user_sessions_active",
            "user_id",
            postgresql_where=db.text("revoked_at IS NULL"),
        ),
    )
