"""Prepared signing envelopes, bound to a scanned private PDF revision.

Preparation is not a cryptographic signature or signed-PDF completion.
"""
from datetime import datetime
from app.extensions import db


class SigningEnvelope(db.Model):
    __tablename__ = "signing_envelopes"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    document_id = db.Column(db.Integer, db.ForeignKey("documents.id"), nullable=False, index=True)
    document_blob_id = db.Column(db.Integer, db.ForeignKey("document_blobs.id"), nullable=False)
    document_sha256 = db.Column(db.String(64), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    state = db.Column(db.String(24), nullable=False, default="draft")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    prepared_at = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)
    __table_args__ = (
        db.CheckConstraint("state IN ('draft','prepared','cancelled')", name="ck_envelope_preparation_state"),
    )


class EnvelopeParticipant(db.Model):
    __tablename__ = "envelope_participants"
    id = db.Column(db.Integer, primary_key=True)
    envelope_id = db.Column(db.Integer, db.ForeignKey("signing_envelopes.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    signing_order = db.Column(db.Integer, nullable=False)
    role = db.Column(db.String(20), nullable=False, default="signer")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("envelope_id", "user_id", name="uq_envelope_participant_user"),
        db.UniqueConstraint("envelope_id", "signing_order", name="uq_envelope_participant_order"),
        db.CheckConstraint("signing_order > 0", name="ck_envelope_participant_order"),
    )
