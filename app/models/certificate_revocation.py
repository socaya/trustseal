"""Immutable CRL observation tied to one retained RFC3161 timestamp.

The signed CRL is preserved verbatim to allow independent replay. A CRL
snapshot is not OCSP, a historical certificate status guarantee, or PAdES-LT.
"""
from datetime import datetime
from app.extensions import db


class CertificateRevocationEvidence(db.Model):
    __tablename__ = "certificate_revocation_evidence"
    id = db.Column(db.BigInteger, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    timestamp_id = db.Column(db.BigInteger, db.ForeignKey("evidence_timestamps.id"), nullable=False, index=True)
    operator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    subject_certificate_sha256 = db.Column(db.String(64), nullable=False)
    issuer_certificate_sha256 = db.Column(db.String(64), nullable=False)
    crl_sha256 = db.Column(db.String(64), nullable=False)
    crl_der_b64 = db.Column(db.Text, nullable=False)
    subject_der_b64 = db.Column(db.Text, nullable=False)
    issuer_der_b64 = db.Column(db.Text, nullable=False)
    this_update = db.Column(db.DateTime, nullable=False)
    next_update = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(16), nullable=False)
    checked_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("timestamp_id", "crl_sha256", name="uq_revocation_timestamp_crl"),
        db.CheckConstraint("status IN ('good','revoked')", name="ck_revocation_evidence_status"),
        db.CheckConstraint("next_update > this_update", name="ck_revocation_evidence_window"),
    )
