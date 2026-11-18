"""External email share grants — magic-link access for recipients
who are NOT members of the owning tenant (DOC-078–DOC-080).

Unlike :class:`TSDShare` (same-tenant grantees matched by user id),
an external share is identified by email and consumed via a one-shot
token delivered by email. Only the SHA-256 of the token is stored.

Permissions are limited to ``view`` or ``comment`` — external
recipients can never edit the source document.

Access is tracked (``consumed_at``, ``access_count``) and the row
is retained after revocation / expiry for audit evidence.
"""
import hashlib
import secrets
from datetime import datetime

from app.extensions import db


EXTERNAL_SHARE_PERMISSIONS = ("view", "comment")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    """URL-safe 40-byte random token (~54 characters)."""
    return secrets.token_urlsafe(40)


class TSDExternalShare(db.Model):
    __tablename__ = "ts_document_external_shares"

    id = db.Column(db.Integer, primary_key=True)
    tsd_id = db.Column(
        db.Integer, db.ForeignKey("ts_documents.id"),
        nullable=False, index=True,
    )
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"),
        nullable=False, index=True,
    )
    recipient_email = db.Column(db.String(255), nullable=False)
    permission = db.Column(db.String(16), nullable=False, default="view")
    token_hash = db.Column(db.String(64), nullable=False, index=True)

    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    revoked_at = db.Column(db.DateTime, index=True)
    consumed_at = db.Column(db.DateTime)
    access_count = db.Column(db.Integer, nullable=False, default=0)
    last_access_at = db.Column(db.DateTime)

    __table_args__ = (
        db.CheckConstraint(
            "permission IN ('view','comment')",
            name="ck_tsd_external_share_permission",
        ),
    )

    def is_active(self, *, now: datetime | None = None) -> bool:
        now = now or datetime.utcnow()
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at <= now:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tsd_id": self.tsd_id,
            "recipient_email": self.recipient_email,
            "permission": self.permission,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "consumed_at": self.consumed_at.isoformat() if self.consumed_at else None,
            "access_count": self.access_count,
            "last_access_at": self.last_access_at.isoformat() if self.last_access_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "active": self.is_active(),
        }
