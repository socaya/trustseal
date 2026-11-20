"""Tenant-scoped Media Library for reusable stamp & letterhead images.

Stores uploaded logos, emblems, signatures, and letterhead graphics so
users can upload once and reuse across stamps, letterheads, and TSD
documents without re-uploading.
"""
from __future__ import annotations

from datetime import datetime

from app.extensions import db


MEDIA_CATEGORIES = ("logo", "emblem", "signature", "letterhead", "general")


class MediaAsset(db.Model):
    __tablename__ = "tsd_media_assets"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"),
        nullable=False, index=True,
    )
    uploaded_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"),
        nullable=False,
    )
    name = db.Column(db.String(140), nullable=False)
    category = db.Column(db.String(24), nullable=False, default="logo", index=True)
    mime_type = db.Column(db.String(64), nullable=False, default="image/png")
    data_uri = db.Column(db.Text, nullable=False)
    width = db.Column(db.Integer, nullable=True)
    height = db.Column(db.Integer, nullable=True)
    size_bytes = db.Column(db.Integer, nullable=False, default=0)
    sha256 = db.Column(db.String(64), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, index=True)

    def to_dict(self, *, include_data: bool = True) -> dict:
        d = {
            "id": self.id,
            "organization_id": self.organization_id,
            "uploaded_by_id": self.uploaded_by_id,
            "name": self.name,
            "category": self.category,
            "mime_type": self.mime_type,
            "width": self.width,
            "height": self.height,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_data:
            d["data_uri"] = self.data_uri
        return d
