"""Immutable OCSP response evidence for a retained TSA certificate.

Only a verified, issuer-signed OCSP response may be saved. No web fetch or
implicit claim of PAdES-LT/LTA compliance.
"""
from datetime import datetime
from app.extensions import db


class OcspEvidence(db.Model):
    __tablename__ = "ocsp_evidence"
    id = db.Column(db.BigInteger, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    timestamp_id = db.Column(db.BigInteger, db.ForeignKey("evidence_timestamps.id"), nullable=False, index=True)
    operator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    subject_certificate_sha256 = db.Column(db.String(64), nullable=False)
    issuer_certificate_sha256 = db.Column(db.String(64), nullable=False)
    response_sha256 = db.Column(db.String(64), nullable=False)
    responder_certificate_sha256 = db.Column(db.String(64))
    responder_der_b64 = db.Column(db.Text)
    response_der_b64 = db.Column(db.Text, nullable=False)
    subject_der_b64 = db.Column(db.Text, nullable=False)
    issuer_der_b64 = db.Column(db.Text, nullable=False)
    produced_at = db.Column(db.DateTime, nullable=False)
    this_update = db.Column(db.DateTime, nullable=False)
    next_update = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(16), nullable=False)
    checked_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("timestamp_id", "response_sha256", name="uq_ocsp_timestamp_response"),
        db.CheckConstraint("status IN ('good','revoked','unknown')", name="ck_ocsp_status"),
        db.CheckConstraint("next_update > this_update", name="ck_ocsp_window"),
    )
