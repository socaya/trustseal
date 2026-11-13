"""Retention records, independently approved legal holds, signed integrity checks."""
from datetime import datetime
from app.extensions import db


class EvidenceRetention(db.Model):
    __tablename__ = "evidence_retentions"
    id = db.Column(db.BigInteger, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    artifact_type = db.Column(db.String(24), nullable=False)
    artifact_id = db.Column(db.BigInteger, nullable=False)
    artifact_sha256 = db.Column(db.String(64), nullable=False)
    retain_until = db.Column(db.DateTime, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("artifact_type", "artifact_id", name="uq_evidence_retention_artifact"),
        db.CheckConstraint("artifact_type IN ('finalized_pdf','stamped_pdf')", name="ck_evidence_retention_type"),
    )


class EvidenceLegalHold(db.Model):
    __tablename__ = "evidence_legal_holds"
    id = db.Column(db.BigInteger, primary_key=True)
    retention_id = db.Column(db.BigInteger, db.ForeignKey("evidence_retentions.id"), nullable=False, index=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    reason = db.Column(db.String(500), nullable=False)
    requested_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    requested_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    released_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    released_at = db.Column(db.DateTime)
    release_reason = db.Column(db.String(500))


class EvidenceCheckpoint(db.Model):
    __tablename__ = "evidence_checkpoints"
    id = db.Column(db.BigInteger, primary_key=True)
    retention_id = db.Column(db.BigInteger, db.ForeignKey("evidence_retentions.id"), nullable=False, index=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    operator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    signature = db.Column(db.Text, nullable=False)
    algorithm = db.Column(db.String(16), nullable=False)
    key_id = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
