"""TSD share grants — give another user access to a TrustSeal Document.

A share is a tenant-scoped grant from the document owner (``created_by``)
to another authenticated user in the same organization. Permission levels:

* ``view``     — may read decrypted content and export PDF
                 (if ``export_policy`` allows it).
* ``comment``  — ``view`` + placeholder for inline comments (phase after
                 this one wires the comments model).
* ``edit``     — ``view`` + may PUT content (bumps the version and
                 snapshots like any other save).

Expiration and revocation are first-class: a grant stops being valid
when ``revoked_at`` is set or ``expires_at`` has passed. Soft state —
rows are retained so the audit trail of who had what access when stays
intact.
"""
from datetime import datetime

from app.extensions import db


TSD_SHARE_PERMISSIONS = ("view", "comment", "edit")


class TSDShare(db.Model):
    __tablename__ = "ts_document_shares"

    id = db.Column(db.Integer, primary_key=True)
    tsd_id = db.Column(
        db.Integer, db.ForeignKey("ts_documents.id"),
        nullable=False, index=True,
    )
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"),
        nullable=False, index=True,
    )

    # Either or both: when a user with matching email is found we bind
    # grantee_user_id at creation time; otherwise we remember the email
    # so the grant can bind when the account is later created.
    grantee_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), index=True,
    )
    grantee_email = db.Column(db.String(255))

    permission = db.Column(db.String(16), nullable=False, default="view")
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False,
    )

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    revoked_at = db.Column(db.DateTime, index=True)

    __table_args__ = (
        db.CheckConstraint(
            "permission IN ('view','comment','edit')",
            name="ck_tsd_share_permission",
        ),
        db.UniqueConstraint(
            "tsd_id", "grantee_user_id",
            name="uq_tsd_share_doc_user",
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
            "grantee_user_id": self.grantee_user_id,
            "grantee_email": self.grantee_email,
            "permission": self.permission,
            "created_by_id": self.created_by_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "active": self.is_active(),
        }
