"""Batch 3 Enterprise Project Management models (PM-23, PM-25, PM-28, PM-29, PM-31, PM-32).

Completes the full 34-module TrustSeal Enterprise Project Management catalogue:
- PM-23: ``ProjectComment`` (threaded collaboration & activity comments)
- PM-25: ``ProjectApprovalRequest`` (governed approvals with subject hash & SoD)
- PM-28: ``ProjectComplianceRecord`` (permits with expiry flagging & restricted HSE incidents)
- PM-29: ``ProjectExternalGrant`` (scoped, revocable, expiring external client/partner portal)
- PM-31: ``ProjectTemplate`` (reusable versioned WBS/budget/gate templates)
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, timezone
from typing import Any

from app.extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_portal_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_portal_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hash_portal_token(raw)


# =====================================================================
# PM-23: COLLABORATION & THREADED COMMENTS
# =====================================================================

class ProjectComment(db.Model):
    __tablename__ = "project_comments"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("project_comments.id"), nullable=True)
    author_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    author_name = db.Column(db.String(140), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "parent_id": self.parent_id,
            "author_user_id": self.author_user_id,
            "author_name": self.author_name,
            "body": self.body,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M UTC") if self.created_at else "",
        }


# =====================================================================
# PM-25: GOVERNED APPROVALS & EVIDENCE BINDING
# =====================================================================

class ProjectApprovalRequest(db.Model):
    __tablename__ = "project_approval_requests"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    subject_type = db.Column(db.String(32), nullable=False, default="deliverable")  # charter, baseline, deliverable, change, closure
    subject_title = db.Column(db.String(220), nullable=False)
    subject_hash = db.Column(db.String(64), nullable=False)
    approval_mode = db.Column(db.String(24), nullable=False, default="internal")   # internal, signature_bound
    enforce_sod = db.Column(db.Boolean, nullable=False, default=True)
    requested_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    decided_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    status = db.Column(db.String(24), nullable=False, default="pending")           # pending, approved, rejected, stale
    decision_note = db.Column(db.Text, nullable=True)
    decided_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "subject_type": self.subject_type or "deliverable",
            "subject_title": self.subject_title,
            "subject_hash": self.subject_hash,
            "approval_mode": self.approval_mode or "internal",
            "enforce_sod": bool(self.enforce_sod),
            "requested_by_id": self.requested_by_id,
            "decided_by_id": self.decided_by_id,
            "status": self.status or "pending",
            "decision_note": self.decision_note or "",
            "decided_at": self.decided_at.strftime("%Y-%m-%d %H:%M UTC") if self.decided_at else "",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
        }


# =====================================================================
# PM-28: COMPLIANCE, PERMITS, SAFEGUARDS & HSE INCIDENTS
# =====================================================================

class ProjectComplianceRecord(db.Model):
    __tablename__ = "project_compliance_records"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    record_type = db.Column(db.String(24), nullable=False, default="permit")  # permit, safeguard, hse_incident, obligation
    title = db.Column(db.String(220), nullable=False)
    authority = db.Column(db.String(160), nullable=True)
    is_mandatory = db.Column(db.Boolean, nullable=False, default=True)
    is_restricted = db.Column(db.Boolean, nullable=False, default=False)
    expiry_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(24), nullable=False, default="active")       # active, expired, closed, investigating
    details = db.Column(db.Text, nullable=True)
    reported_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    def is_expired(self, today: date | None = None) -> bool:
        if not self.expiry_date:
            return False
        return self.expiry_date < (today or date.today())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "record_type": self.record_type or "permit",
            "title": self.title,
            "authority": self.authority or "",
            "is_mandatory": bool(self.is_mandatory),
            "is_restricted": bool(self.is_restricted),
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else "",
            "is_expired": self.is_expired(),
            "status": "expired" if self.is_expired() and self.status == "active" else (self.status or "active"),
            "details": self.details or "",
        }


# =====================================================================
# PM-29: EXTERNAL CLIENT & PARTNER COLLABORATION PORTAL GRANTS
# =====================================================================

class ProjectExternalGrant(db.Model):
    __tablename__ = "project_external_grants"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    recipient_name = db.Column(db.String(160), nullable=False)
    recipient_email = db.Column(db.String(180), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    scope_json = db.Column(db.JSON, nullable=False, default=dict)  # e.g. {"milestones": True, "summary": True}
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    granted_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    def is_valid(self) -> bool:
        if self.revoked_at is not None:
            return False
        now = _utcnow()
        exp = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=timezone.utc)
        return exp > now

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "recipient_name": self.recipient_name,
            "recipient_email": self.recipient_email,
            "scope": self.scope_json or {},
            "expires_at": self.expires_at.strftime("%Y-%m-%d %H:%M UTC") if self.expires_at else "",
            "revoked": self.revoked_at is not None,
            "is_valid": self.is_valid(),
        }


# =====================================================================
# PM-31: REUSABLE PROJECT TEMPLATES & CONFIGURATION
# =====================================================================

class ProjectTemplate(db.Model):
    __tablename__ = "project_templates"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    code = db.Column(db.String(40), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(48), nullable=False, default="client_delivery")
    delivery_methodology = db.Column(db.String(24), nullable=False, default="hybrid")
    version = db.Column(db.Integer, nullable=False, default=1)
    default_wbs_json = db.Column(db.JSON, nullable=False, default=list)
    default_gates_json = db.Column(db.JSON, nullable=False, default=list)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "category": self.category or "client_delivery",
            "delivery_methodology": self.delivery_methodology or "hybrid",
            "version": int(self.version or 1),
            "default_wbs": self.default_wbs_json or [],
            "default_gates": self.default_gates_json or [],
        }
