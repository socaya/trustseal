"""Signature Registration Approval, Usage Audit Log, and Owner OTP Verification."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from app.extensions import db


class SignatureApprovalState(db.Model):
    """Tracks approval status & device/engine metadata for each SignatureProfile."""
    __tablename__ = "signature_approval_states"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    signature_profile_id = db.Column(
        db.Integer, db.ForeignKey("signature_profiles.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    approval_status = db.Column(db.String(24), nullable=False, default="pending")  # pending | approved | revoked
    capture_engine = db.Column(db.String(40), nullable=False, default="ts_hq_engine")  # device_pad | stylus_pen | ts_hq_engine | uploaded
    device_name = db.Column(db.String(120), nullable=True)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class SignatureUsageLog(db.Model):
    """Immutable audit & OTP approval record for every attempt to apply a registered signature."""
    __tablename__ = "signature_usage_logs"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    signature_profile_id = db.Column(
        db.Integer, db.ForeignKey("signature_profiles.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    requester_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    document_id = db.Column(db.Integer, nullable=True, index=True)
    document_title = db.Column(db.String(240), nullable=True)

    otp_code_hash = db.Column(db.String(64), nullable=False)
    otp_last2 = db.Column(db.String(4), nullable=True)
    otp_expires_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(24), nullable=False, default="otp_pending")  # otp_pending | approved | applied | denied | expired

    ip_address = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    approved_at = db.Column(db.DateTime, nullable=True)
    applied_at = db.Column(db.DateTime, nullable=True)

    @staticmethod
    def hash_otp(code: str) -> str:
        return hashlib.sha256(str(code).strip().encode("utf-8")).hexdigest()

    @staticmethod
    def generate_otp() -> str:
        return f"{secrets.randbelow(900000) + 100000:06d}"

    def is_expired(self) -> bool:
        return datetime.utcnow() > (self.otp_expires_at or datetime.utcnow())

    def verify_otp(self, code: str) -> bool:
        if self.is_expired():
            return False
        return secrets.compare_digest(self.otp_code_hash, self.hash_otp(code))


def ensure_signature_governance_tables() -> None:
    """Create governance tables idempotently if not yet migrated."""
    try:
        SignatureApprovalState.__table__.create(db.engine, checkfirst=True)
        SignatureUsageLog.__table__.create(db.engine, checkfirst=True)
    except Exception:
        pass
