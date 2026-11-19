"""Physical stamp device profile (§5 + §15).

Captures manufacturer/model, imprint area, supported shapes/colours,
minimum stroke width, and date-band availability. Stamp designs can
link to a DeviceProfile so the Studio can warn about incompatibilities
before export.
"""
from datetime import datetime

from app.extensions import db


MECHANISMS = (
    "self_inking", "rubber", "pre_inked",
    "embossed", "wax", "digital",
)


class DeviceProfile(db.Model):
    __tablename__ = "device_profiles"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), nullable=False, unique=True)
    name = db.Column(db.String(160), nullable=False)
    manufacturer = db.Column(db.String(80), nullable=False)
    model = db.Column(db.String(80), nullable=False)
    mechanism = db.Column(db.String(32), nullable=False)
    imprint_w_mm = db.Column(db.Numeric(6, 2), nullable=False)
    imprint_h_mm = db.Column(db.Numeric(6, 2), nullable=False)
    shape_hint = db.Column(db.String(16), nullable=False, default="rect")
    supported_shapes = db.Column(db.JSON, nullable=False)
    supported_colors = db.Column(db.JSON, nullable=False)
    max_colors = db.Column(db.Integer, nullable=False, default=1)
    min_stroke_mm = db.Column(db.Numeric(4, 2), nullable=False, default=0.30)
    has_date_band = db.Column(db.Boolean, nullable=False, default=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.CheckConstraint(
            "mechanism IN ('self_inking','rubber','pre_inked',"
            "'embossed','wax','digital')",
            name="ck_device_mechanism",
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "slug": self.slug,
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "mechanism": self.mechanism,
            "imprint_w_mm": float(self.imprint_w_mm),
            "imprint_h_mm": float(self.imprint_h_mm),
            "shape_hint": self.shape_hint,
            "supported_shapes": self.supported_shapes or [],
            "supported_colors": self.supported_colors or [],
            "max_colors": self.max_colors,
            "min_stroke_mm": float(self.min_stroke_mm),
            "has_date_band": self.has_date_band,
            "notes": self.notes,
        }
