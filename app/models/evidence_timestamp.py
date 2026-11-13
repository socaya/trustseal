"""RFC 3161 timestamp response evidence for an immutable PDF artifact.

A timestamp is a detached token against the exact output PDF digest. It is not
embedded into the PDF and does not establish PAdES-LT/LTA compliance.
"""
from datetime import datetime
from app.extensions import db


class EvidenceTimestamp(db.Model):
    __tablename__ = "evidence_timestamps"
    id = db.Column(db.BigInteger, primary_key=True)
    retention_id = db.Column(db.BigInteger, db.ForeignKey("evidence_retentions.id"), nullable=False, index=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    operator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    artifact_sha256 = db.Column(db.String(64), nullable=False)
    tsa_certificate_sha256 = db.Column(db.String(64), nullable=False)
    token_sha256 = db.Column(db.String(64), nullable=False)
    token_der_b64 = db.Column(db.Text, nullable=False)
    gen_time = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("retention_id", "token_sha256", name="uq_evidence_timestamp_token"),
    )
