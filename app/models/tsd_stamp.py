"""TrustSeal Documents stamp designs — tenant-owned SVG stamps.

Designed in the browser Stamp Studio, registered against a tenant and
reusable across any TSD. These are distinct from ``ManagedStamp`` +
``StampDesignVersion`` which carry the full custody / approval
workflow for cryptographically-attested PDF seals. A ``TSDStamp`` is a
visual mark: you can drop it inline into a document body or (in a
later phase) rasterise it into a signed PDF appearance.

Kinds
    * ``seal``       — round organisation seal with text around the
                       circumference and center text
    * ``date``       — rectangular date stamp with a label ribbon
                       (RECEIVED / APPROVED / PAID / etc.) and the
                       stamped date
    * ``rubber``     — rectangular rubber stamp with freeform text
    * ``custom``     — a raw SVG the user provides

Each design stores:

* The chosen ``kind`` and the ``layout`` JSON describing it (text,
  colours, outer / inner ring radius, border style, fonts).
* The rendered ``svg`` string, served back verbatim when inserting
  the stamp into a document.
* A monochrome 160×160 ``preview_svg`` used for the library grid.
"""
from datetime import datetime

from app.extensions import db


TSD_STAMP_KINDS = ("seal", "date", "company_dated", "rubber", "custom")


class TSDStamp(db.Model):
    __tablename__ = "tsd_stamps"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"),
        nullable=False, index=True,
    )
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False,
    )
    name = db.Column(db.String(120), nullable=False)
    kind = db.Column(db.String(16), nullable=False, default="seal")
    layout = db.Column(db.JSON, nullable=False)   # design parameters
    svg = db.Column(db.Text, nullable=False)      # rendered SVG
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at = db.Column(db.DateTime, index=True)

    __table_args__ = (
        db.CheckConstraint(
            "kind IN ('seal','date','company_dated','rubber','custom')",
            name="ck_tsd_stamp_kind",
        ),
        db.UniqueConstraint(
            "organization_id", "name",
            name="uq_tsd_stamp_org_name",
        ),
    )

    def to_dict(self, *, include_svg: bool = True) -> dict:
        d = {
            "id": self.id,
            "organization_id": self.organization_id,
            "created_by_id": self.created_by_id,
            "name": self.name,
            "kind": self.kind,
            "layout": self.layout,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_svg:
            d["svg"] = self.svg
        return d
