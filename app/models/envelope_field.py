"""Per-participant signing fields.

Each row is one rectangle on one page assigned to one participant.
The signer sees only the rows where ``participant_id`` matches them;
the creator sees every row. ``field_type`` names the UI control
(signature, initials, date, text, checkbox); ``value`` captures the
submitted value once the signer acknowledges.

Coordinates use the PDF user-space convention (origin at bottom-left,
units in points). Rectangles are stored as (x_pt, y_pt, width_pt,
height_pt) where (x_pt, y_pt) is the lower-left corner. Rendering
code must respect that convention.

Invariants:

* Only draft envelopes may add / remove fields; prepared envelopes
  are immutable for field placement.
* A ``required=True`` field must be assigned to exactly one
  participant and that participant must be of role
  ``signer`` (not witness).
* ``value`` and ``submitted_at`` are non-null exactly together, and
  only after the owning participant's ``SignerDecision`` lands.
"""
from datetime import datetime

from app.extensions import db

FIELD_TYPES = ("signature", "initials", "date", "text", "checkbox")


class EnvelopeField(db.Model):
    __tablename__ = "envelope_fields"

    id = db.Column(db.BigInteger, primary_key=True)
    envelope_id = db.Column(
        db.Integer,
        db.ForeignKey("signing_envelopes.id"),
        nullable=False,
        index=True,
    )
    participant_id = db.Column(
        db.Integer,
        db.ForeignKey("envelope_participants.id"),
        nullable=False,
        index=True,
    )
    field_type = db.Column(db.String(20), nullable=False)
    label = db.Column(db.String(100), nullable=True)
    page_number = db.Column(db.Integer, nullable=False)
    x_pt = db.Column(db.Numeric(10, 3), nullable=False)
    y_pt = db.Column(db.Numeric(10, 3), nullable=False)
    width_pt = db.Column(db.Numeric(10, 3), nullable=False)
    height_pt = db.Column(db.Numeric(10, 3), nullable=False)
    required = db.Column(
        db.Boolean, nullable=False, default=True, server_default=db.text("true")
    )
    value = db.Column(db.Text, nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )

    __table_args__ = (
        db.CheckConstraint(
            "field_type IN ('signature','initials','date','text','checkbox')",
            name="ck_envelope_field_type",
        ),
        db.CheckConstraint(
            "page_number > 0", name="ck_envelope_field_page"
        ),
        db.CheckConstraint(
            "width_pt > 0 AND height_pt > 0",
            name="ck_envelope_field_rect",
        ),
    )
