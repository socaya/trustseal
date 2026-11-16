"""Reusable envelope templates (Phase S1).

An operator frequently re-sends the same shape of envelope — same
routing, same reminder cadence, same recipient roster — against a
fresh document. Templates capture that shape so a draft envelope
can be produced in a single API call, reducing repeated setup.
"""
from datetime import datetime

from app.extensions import db


class EnvelopeTemplate(db.Model):
    __tablename__ = "envelope_templates"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(400), nullable=True)
    routing_mode = db.Column(
        db.String(20),
        nullable=False,
        default="sequential",
        server_default="sequential",
    )
    quorum_required = db.Column(db.Integer, nullable=True)
    reminder_cooloff_hours = db.Column(db.Integer, nullable=True)
    reminder_max_count = db.Column(db.Integer, nullable=True)
    # Relative expiry — resolved to an absolute ``expires_at`` on
    # instantiation. A NULL value leaves the instantiated envelope
    # with no auto-expiry.
    expires_in_hours = db.Column(db.Integer, nullable=True)
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "organization_id", "name", name="uq_envelope_template_org_name"
        ),
        db.CheckConstraint(
            "routing_mode IN ('sequential','parallel','quorum')",
            name="ck_envelope_template_routing_mode",
        ),
        db.CheckConstraint(
            "(routing_mode = 'quorum' AND quorum_required IS NOT NULL AND quorum_required > 0) "
            "OR (routing_mode <> 'quorum' AND quorum_required IS NULL)",
            name="ck_envelope_template_quorum_required",
        ),
        db.CheckConstraint(
            "reminder_cooloff_hours IS NULL OR reminder_cooloff_hours BETWEEN 1 AND 720",
            name="ck_envelope_template_reminder_cooloff_range",
        ),
        db.CheckConstraint(
            "reminder_max_count IS NULL OR reminder_max_count BETWEEN 1 AND 50",
            name="ck_envelope_template_reminder_max_count_range",
        ),
        db.CheckConstraint(
            "expires_in_hours IS NULL OR expires_in_hours BETWEEN 1 AND 8760",
            name="ck_envelope_template_expires_in_hours_range",
        ),
        db.CheckConstraint(
            "char_length(name) >= 1",
            name="ck_envelope_template_name_present",
        ),
    )


class EnvelopeTemplateParticipant(db.Model):
    __tablename__ = "envelope_template_participants"

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(
        db.Integer,
        db.ForeignKey("envelope_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    signing_order = db.Column(db.Integer, nullable=False)
    role = db.Column(
        db.String(20),
        nullable=False,
        default="signer",
        server_default="signer",
    )
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        db.UniqueConstraint(
            "template_id", "user_id", name="uq_envelope_template_user"
        ),
        db.UniqueConstraint(
            "template_id",
            "signing_order",
            name="uq_envelope_template_order",
        ),
        db.CheckConstraint(
            "signing_order > 0",
            name="ck_envelope_template_order",
        ),
        db.CheckConstraint(
            "role IN ('signer','witness')",
            name="ck_envelope_template_role",
        ),
    )
