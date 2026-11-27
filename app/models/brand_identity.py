"""TRUSTSEAL Brand Identity Studio data models.

Stores tenant-scoped Brand Identity Kits containing parametric logo settings,
generated vector SVGs (primary, dark mono, light mono, square icon), complete
Brand Guidelines specifications (HEX/RGB/CMYK palettes, typography, clear-space,
usage rules), and optional link to TRUSTSEAL Media Library.
"""
from __future__ import annotations

import secrets
from datetime import datetime

from app.extensions import db


class BrandIdentityKit(db.Model):
    __tablename__ = "brand_identity_kits"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    kit_ref = db.Column(db.String(40), nullable=False, unique=True, index=True)

    # Core Brand Identity Parameters
    brand_name = db.Column(db.String(140), nullable=False)
    tagline = db.Column(db.String(220), nullable=True)
    industry = db.Column(db.String(80), nullable=False, default="Technology & Enterprise")
    archetype = db.Column(db.String(40), nullable=False, default="modern_corporate")
    # modern_corporate | luxury_editorial | tech_minimal | bold_geometric | heritage_emblem | eco_organic

    # Logo Composition Parameters
    icon_id = db.Column(db.String(48), nullable=False, default="shield_check")
    logo_layout = db.Column(db.String(24), nullable=False, default="horizontal")
    # horizontal | stacked | emblem | monogram | wordmark
    font_heading = db.Column(db.String(80), nullable=False, default="Inter")
    font_body = db.Column(db.String(80), nullable=False, default="Inter")
    letter_spacing = db.Column(db.Float, nullable=False, default=1.5)
    icon_scale = db.Column(db.Float, nullable=False, default=1.0)

    # Color System
    primary_color = db.Column(db.String(16), nullable=False, default="#002769")
    secondary_color = db.Column(db.String(16), nullable=False, default="#02982e")
    accent_color = db.Column(db.String(16), nullable=False, default="#1d4ed8")
    dark_color = db.Column(db.String(16), nullable=False, default="#0f172a")
    light_color = db.Column(db.String(16), nullable=False, default="#f4f7fc")

    # Generated Vector Assets & Guidelines JSON
    primary_svg = db.Column(db.Text, nullable=True)
    mono_dark_svg = db.Column(db.Text, nullable=True)
    mono_light_svg = db.Column(db.Text, nullable=True)
    icon_only_svg = db.Column(db.Text, nullable=True)
    guidelines_json = db.Column(db.JSON, nullable=True)

    # Optional bridge to TRUSTSEAL Media Library (for Letterheads, Stamps, TS Docs)
    media_asset_id = db.Column(db.Integer, db.ForeignKey("tsd_media_assets.id", ondelete="SET NULL"), nullable=True)

    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def generate_ref(org_id: int) -> str:
        return f"BRD-{datetime.utcnow().year}-{org_id:02d}{secrets.token_hex(3).upper()}"

    def to_dict(self, *, include_svgs: bool = True) -> dict:
        out = {
            "id": self.id,
            "kit_ref": self.kit_ref,
            "organization_id": self.organization_id,
            "brand_name": self.brand_name,
            "tagline": self.tagline or "",
            "industry": self.industry,
            "archetype": self.archetype,
            "icon_id": self.icon_id,
            "logo_layout": self.logo_layout,
            "font_heading": self.font_heading,
            "font_body": self.font_body,
            "letter_spacing": self.letter_spacing,
            "icon_scale": self.icon_scale,
            "primary_color": self.primary_color,
            "secondary_color": self.secondary_color,
            "accent_color": self.accent_color,
            "dark_color": self.dark_color,
            "light_color": self.light_color,
            "media_asset_id": self.media_asset_id,
            "guidelines": self.guidelines_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_svgs:
            out["primary_svg"] = self.primary_svg
            out["mono_dark_svg"] = self.mono_dark_svg
            out["mono_light_svg"] = self.mono_light_svg
            out["icon_only_svg"] = self.icon_only_svg
        return out


def ensure_brand_studio_tables() -> None:
    """Create Brand Identity Studio tables idempotently."""
    try:
        BrandIdentityKit.__table__.create(db.engine, checkfirst=True)
    except Exception:
        pass
