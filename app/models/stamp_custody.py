"""Tenant-scoped governed electronic stamp custody and issuance metadata.

A signed stamp attestation is separate from placing an image or PDF seal.
Legacy DigitalStamp remains an unsupported generic CRUD schema.
"""
from datetime import datetime
from app.extensions import db


class ManagedStamp(db.Model):
    __tablename__ = "managed_stamps"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    code = db.Column(db.String(32), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    custodian_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    status = db.Column(db.String(20), nullable=False, default="pending")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime)
    revoked_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    revoked_at = db.Column(db.DateTime)
    __table_args__ = (
        db.UniqueConstraint("organization_id", "code", name="uq_managed_stamp_org_code"),
        db.CheckConstraint("status IN ('pending','active','revoked')", name="ck_managed_stamp_status"),
    )


class StampApplication(db.Model):
    __tablename__ = "stamp_applications"
    id = db.Column(db.Integer, primary_key=True)
    stamp_id = db.Column(db.Integer, db.ForeignKey("managed_stamps.id"), nullable=False, index=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    finalized_pdf_id = db.Column(db.BigInteger, db.ForeignKey("finalized_pdfs.id"), nullable=False)
    source_sha256 = db.Column(db.String(64), nullable=False)
    evidence_sha256 = db.Column(db.String(64), nullable=False)
    requested_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    reason = db.Column(db.String(240), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    requested_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    decided_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    decided_at = db.Column(db.DateTime)
    __table_args__ = (
        db.UniqueConstraint("stamp_id", "finalized_pdf_id", name="uq_stamp_application_pdf"),
        db.CheckConstraint("status IN ('pending','approved','rejected')", name="ck_stamp_application_status"),
    )


class StampAttestation(db.Model):
    __tablename__ = "stamp_attestations"
    id = db.Column(db.BigInteger, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("stamp_applications.id"), nullable=False, unique=True)
    stamp_id = db.Column(db.Integer, db.ForeignKey("managed_stamps.id"), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    operator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    algorithm = db.Column(db.String(16), nullable=False)
    key_id = db.Column(db.String(80), nullable=False)
    signature = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
