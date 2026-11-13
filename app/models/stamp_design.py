"""Immutable approved graphical stamp design versions.

A design is a versioned record, not a mutable filesystem image. Artwork is
limited to a validated compact PNG with a retained SHA-256. Publication needs
an independent administrator, distinct from the author and stamp custodian.
"""
from datetime import datetime
from app.extensions import db


class StampDesignVersion(db.Model):
    __tablename__ = "stamp_design_versions"
    id = db.Column(db.BigInteger, primary_key=True)
    stamp_id = db.Column(db.Integer, db.ForeignKey("managed_stamps.id"), nullable=False, index=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    version = db.Column(db.Integer, nullable=False)
    layout = db.Column(db.JSON, nullable=False)
    logo_png_b64 = db.Column(db.Text)
    logo_sha256 = db.Column(db.String(64))
    design_sha256 = db.Column(db.String(64), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    state = db.Column(db.String(16), nullable=False, default="pending")
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    approved_at = db.Column(db.DateTime)
    __table_args__ = (
        db.UniqueConstraint("stamp_id", "version", name="uq_stamp_design_version"),
        db.CheckConstraint("version > 0", name="ck_stamp_design_version"),
        db.CheckConstraint("state IN ('pending','approved','rejected')", name="ck_stamp_design_state"),
    )
