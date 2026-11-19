"""Signed receipt for a stamp instance inserted into a TSD.

A fresh row is written every time the TSD editor calls
``POST /api/tsd-stamps/<id>/receipt``. The row is the authoritative
server-side record; the inserted SVG embeds only the receipt id and
nonce so that any viewer can call ``/verify-receipt`` and get an
independently signed assertion that this stamp impression is
authentic — including who placed it and when.
"""
from datetime import datetime

from app.extensions import db


class TSDStampInsertion(db.Model):
    __tablename__ = "tsd_stamp_insertions"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"),
        nullable=False, index=True,
    )
    stamp_id = db.Column(
        db.Integer, db.ForeignKey("tsd_stamps.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    document_id = db.Column(
        db.Integer, db.ForeignKey("ts_documents.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    placed_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False,
    )
    placed_at = db.Column(db.DateTime, nullable=False,
                          default=datetime.utcnow, index=True)

    # Free-text label the editor sent ("Signature block", "Approval",
    # or the document title at insertion time) for the audit viewer.
    context_label = db.Column(db.String(200))

    # SHA-256 of the canonical stamp SVG at insertion time — so even a
    # later edit of the stamp design can't invalidate past impressions.
    context_hash = db.Column(db.String(64), nullable=False)

    nonce = db.Column(db.String(32), nullable=False)
    hmac_hex = db.Column(db.String(64), nullable=False)
    key_version = db.Column(db.Integer, nullable=False, default=1)

    revoked_at = db.Column(db.DateTime)
    revoked_reason = db.Column(db.String(200))

    __table_args__ = (
        db.UniqueConstraint("stamp_id", "nonce",
                            name="uq_tsd_stamp_insertion_nonce"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "stamp_id": self.stamp_id,
            "document_id": self.document_id,
            "placed_by_id": self.placed_by_id,
            "placed_at": self.placed_at.isoformat() if self.placed_at else None,
            "context_label": self.context_label,
            "nonce": self.nonce,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "revoked_reason": self.revoked_reason,
        }
