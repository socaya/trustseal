"""Immutable validation dossier for retained PDF/timestamp/revocation evidence.

Dossiers are point-in-time observations, never automatic qualified trust verdicts.
"""
from datetime import datetime
from app.extensions import db


class ValidationDossier(db.Model):
    __tablename__ = "validation_dossiers"
    id = db.Column(db.BigInteger, primary_key=True)
    retention_id = db.Column(db.BigInteger, db.ForeignKey("evidence_retentions.id"), nullable=False, index=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    operator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    timestamp_id = db.Column(db.BigInteger, db.ForeignKey("evidence_timestamps.id"), nullable=False)
    manifest = db.Column(db.JSON, nullable=False)
    manifest_sha256 = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("retention_id", "timestamp_id", "manifest_sha256",
                            name="uq_validation_dossier_snapshot"),
    )
