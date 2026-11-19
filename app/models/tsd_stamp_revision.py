"""Immutable snapshot of a stamp design (§15).

A new revision is written every time a stamp transitions to
``published`` status. The row freezes the layout JSON + rendered SVG
+ name as they were at publication time, so audits and inserted
receipts always have a stable artefact to point at — independent of
any later draft edits.
"""
from datetime import datetime

from app.extensions import db


class TSDStampRevision(db.Model):
    __tablename__ = "tsd_stamp_revisions"

    id = db.Column(db.Integer, primary_key=True)
    stamp_id = db.Column(
        db.Integer, db.ForeignKey("tsd_stamps.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    version = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False,
    )
    status_at_snapshot = db.Column(db.String(16), nullable=False)
    layout = db.Column(db.JSON, nullable=False)
    svg = db.Column(db.Text, nullable=False)
    name_at_snapshot = db.Column(db.String(120), nullable=False)
    notes = db.Column(db.Text)

    __table_args__ = (
        db.UniqueConstraint("stamp_id", "version",
                            name="uq_stamp_revision_version"),
    )

    def to_dict(self, *, include_svg: bool = False) -> dict:
        d = {
            "id": self.id,
            "stamp_id": self.stamp_id,
            "version": self.version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by_id": self.created_by_id,
            "status_at_snapshot": self.status_at_snapshot,
            "name_at_snapshot": self.name_at_snapshot,
            "notes": self.notes,
            "layout": self.layout,
        }
        if include_svg:
            d["svg"] = self.svg
        return d
