"""Enterprise Contract Lifecycle Management (CLM) models for TrustSeal Documents.

Implements:
- ``Project``: Tenant-scoped operational project governing one or more contracts.
- ``ContractTemplate``: Versioned, publishable contract templates with variable
  schemas, default Key Terms blueprints, and default Deliverable schedules.
- ``ContractWorkflow``: Canonical contract record backed 1:1 by ``TSDocument``,
  enforcing canonical statuses (``DRAFT``, ``SIGNED``, ``SUSPENDED``,
  ``TERMINATED``) alongside operational workflow sub-stages.
- ``ContractKeyTerm``: Structured key terms & first-class Probation tracking.
- ``ContractDeliverable``: Project milestones, payment tranches & acceptance gates.
- ``ContractObligation``: General post-execution commitments.
"""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import inspect, text

from app.extensions import db


CONTRACT_STATUSES = (
    ("DRAFT",      "Draft"),
    ("SIGNED",     "Signed"),
    ("SUSPENDED",  "Suspended"),
    ("TERMINATED", "Terminated"),
)

CONTRACT_STATUS_LABELS = dict(CONTRACT_STATUSES)

WORKFLOW_STAGES = (
    ("draft",       "Draft"),
    ("review",      "Legal Review"),
    ("negotiation", "Negotiation"),
    ("approval",    "Pending Approval"),
    ("signature",   "Agreement Signing"),
    ("signed",      "Active / Executed"),
    ("suspended",   "Suspended"),
    ("expired",     "Terminated / Expired"),
    ("closed",      "Archived / Void"),
)

STAGE_LABELS = dict(WORKFLOW_STAGES)

# Stages where the underlying TSD document body is edit-locked
LOCKED_STAGES = frozenset({"approval", "signature", "signed", "suspended", "expired", "closed"})

PROJECT_CATEGORIES = (
    ("client_delivery",  "Client Delivery"),
    ("procurement",      "Procurement & Vendor"),
    ("hr_onboarding",    "HR & Employment"),
    ("real_estate",      "Real Estate & Leases"),
    ("internal_ops",     "Internal Operations"),
    ("legal_governance", "Legal & Governance"),
)

CONTRACT_TYPES = (
    ("msa",                  "Master Service Agreement (MSA)"),
    ("sow",                  "Project Statement of Work (SOW)"),
    ("fixed_price",          "Fixed-Price Delivery Contract"),
    ("employment_probation", "Employment Contract (Probation)"),
    ("employment_permanent", "Permanent Employment Agreement"),
    ("contractor",           "Consultancy / Contractor Agreement"),
    ("vendor_supply",        "Vendor & Supply Agreement"),
    ("saas_subscription",    "SaaS / Licensing Agreement"),
    ("commercial_lease",     "Commercial Lease Agreement"),
    ("nda",                  "Mutual Non-Disclosure Agreement"),
    ("dpa",                  "Data Processing Agreement (DPA)"),
    ("amendment",            "Amendment"),
    ("addendum",             "Addendum"),
    ("renewal",              "Renewal"),
)


class Project(db.Model):
    """Tenant-scoped project that governs one or more Contracts."""

    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    project_code = db.Column(db.String(40), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(48), nullable=False, default="client_delivery")
    client_name = db.Column(db.String(200), nullable=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    status = db.Column(db.String(24), nullable=False, default="active")
    lifecycle_state = db.Column(db.String(32), nullable=False, default="executing", index=True)
    delivery_methodology = db.Column(db.String(24), nullable=False, default="hybrid")
    portfolio_id = db.Column(db.Integer, db.ForeignKey("project_portfolios.id"), nullable=True, index=True)
    programme_id = db.Column(db.Integer, db.ForeignKey("project_programmes.id"), nullable=True, index=True)
    sponsor_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    confidentiality = db.Column(db.String(24), nullable=False, default="internal")
    budget_amount = db.Column(db.Float, nullable=True)
    budget_numeric = db.Column(db.Numeric(18, 2), nullable=True)
    currency = db.Column(db.String(12), nullable=False, default="USD")
    start_date = db.Column(db.String(32), nullable=True)
    end_date = db.Column(db.String(32), nullable=True)
    start_date_typed = db.Column(db.Date, nullable=True)
    end_date_typed = db.Column(db.Date, nullable=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def effective_budget_decimal(self):
        from decimal import Decimal
        if self.budget_numeric is not None:
            return Decimal(self.budget_numeric)
        if self.budget_amount is not None:
            return Decimal(str(self.budget_amount)).quantize(Decimal("0.01"))
        return Decimal("0.00")

    def to_dict(self) -> dict:
        eff_budget = self.effective_budget_decimal()
        return {
            "id": self.id,
            "project_code": self.project_code,
            "name": self.name,
            "description": self.description or "",
            "category": self.category or "client_delivery",
            "client_name": self.client_name or "",
            "owner_user_id": self.owner_user_id,
            "sponsor_user_id": self.sponsor_user_id,
            "portfolio_id": self.portfolio_id,
            "programme_id": self.programme_id,
            "status": self.status or "active",
            "lifecycle_state": self.lifecycle_state or "executing",
            "delivery_methodology": self.delivery_methodology or "hybrid",
            "confidentiality": self.confidentiality or "internal",
            "budget_amount": float(eff_budget) if (self.budget_numeric is not None or self.budget_amount is not None) else None,
            "budget_numeric": str(eff_budget) if (self.budget_numeric is not None or self.budget_amount is not None) else None,
            "currency": self.currency or "USD",
            "start_date": self.start_date_typed.isoformat() if self.start_date_typed else (self.start_date or ""),
            "end_date": self.end_date_typed.isoformat() if self.end_date_typed else (self.end_date or ""),
            "version": int(self.version or 1),
            "is_default": bool(self.is_default),
            "created_at": self.created_at.strftime("%Y-%m-%d") if self.created_at else "",
        }


class ContractTemplate(db.Model):
    """Governed Contract Template with variable schema, Key Terms & Deliverable blueprints."""

    __tablename__ = "contract_templates"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    contract_type = db.Column(db.String(48), nullable=False, default="msa")
    default_project_category = db.Column(db.String(48), nullable=False, default="client_delivery")
    state = db.Column(db.String(20), nullable=False, default="draft")  # draft, published, archived
    version = db.Column(db.Integer, nullable=False, default=1)
    body_html = db.Column(db.Text, nullable=False, default="")
    variables_json = db.Column(db.JSON, nullable=False, default=list)
    default_key_terms_json = db.Column(db.JSON, nullable=False, default=list)
    default_deliverables_json = db.Column(db.JSON, nullable=False, default=list)
    policy_json = db.Column(db.JSON, nullable=False, default=dict)
    default_letterhead_id = db.Column(db.Integer, nullable=True)
    default_stamp_id = db.Column(db.Integer, nullable=True)
    is_system = db.Column(db.Boolean, nullable=False, default=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    published_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "contract_type": self.contract_type or "msa",
            "default_project_category": self.default_project_category or "client_delivery",
            "state": self.state or "draft",
            "version": self.version or 1,
            "body_html": self.body_html or "",
            "variables": self.variables_json or [],
            "default_key_terms": self.default_key_terms_json or [],
            "default_deliverables": self.default_deliverables_json or [],
            "policy": self.policy_json or {},
            "default_letterhead_id": self.default_letterhead_id,
            "default_stamp_id": self.default_stamp_id,
            "is_system": bool(self.is_system),
            "published_at": self.published_at.strftime("%Y-%m-%d %H:%M UTC") if self.published_at else "",
        }


class ContractWorkflow(db.Model):
    __tablename__ = "contract_workflows"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    document_id = db.Column(
        db.Integer, db.ForeignKey("ts_documents.id"), nullable=False, unique=True, index=True
    )
    project_id = db.Column(
        db.Integer, db.ForeignKey("projects.id"), nullable=True, index=True
    )
    template_id = db.Column(
        db.Integer, db.ForeignKey("contract_templates.id"), nullable=True
    )

    # Canonical contract status: DRAFT | SIGNED | SUSPENDED | TERMINATED
    contract_status = db.Column(db.String(20), nullable=False, default="DRAFT", index=True)
    # Fine-grained workflow sub-stage
    stage = db.Column(db.String(24), nullable=False, default="draft")

    contract_number = db.Column(db.String(64), nullable=True)
    contract_type = db.Column(db.String(48), nullable=False, default="msa")
    counterparty_name = db.Column(db.String(200), nullable=True)
    deal_value = db.Column(db.String(64), nullable=True)
    currency = db.Column(db.String(12), nullable=False, default="USD")
    effective_date = db.Column(db.String(32), nullable=True)
    expiration_date = db.Column(db.String(32), nullable=True)
    governing_law = db.Column(db.String(120), nullable=True)
    letterhead_id = db.Column(db.Integer, nullable=True)
    stamp_id = db.Column(db.Integer, nullable=True)

    # Renewal & governance fields
    renewal_type = db.Column(db.String(24), nullable=False, default="none")
    notice_period_days = db.Column(db.Integer, nullable=False, default=30)
    renewal_term_months = db.Column(db.Integer, nullable=True)
    routing_mode = db.Column(db.String(24), nullable=False, default="parallel")
    edit_locked = db.Column(db.Boolean, nullable=False, default=False)

    # Links to Trust & Compliance + Lineage
    evidence_retention_id = db.Column(db.Integer, nullable=True)
    stamp_receipt_id = db.Column(db.Integer, nullable=True)
    parent_contract_id = db.Column(db.Integer, nullable=True, index=True)
    relationship_type = db.Column(db.String(24), nullable=True)

    # JSON blobs for flexible checklist, signatories, and chronological audit trail
    checklist_json = db.Column(db.JSON, nullable=False, default=dict)
    signers_json = db.Column(db.JSON, nullable=False, default=list)
    events_json = db.Column(db.JSON, nullable=False, default=list)

    closed_at = db.Column(db.DateTime, nullable=True)
    execution_sha256 = db.Column(db.String(64), nullable=True)

    # Suspension fields
    suspended_at = db.Column(db.DateTime, nullable=True)
    suspension_reason = db.Column(db.String(500), nullable=True)
    expected_resume_date = db.Column(db.String(32), nullable=True)

    # Termination fields
    terminated_at = db.Column(db.DateTime, nullable=True)
    termination_type = db.Column(db.String(32), nullable=True)
    termination_reason = db.Column(db.String(500), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def canonical_status(self) -> str:
        raw = (self.contract_status or "").strip().upper()
        if raw in CONTRACT_STATUS_LABELS:
            return raw
        if self.stage == "signed":
            return "SIGNED"
        if self.stage == "suspended":
            return "SUSPENDED"
        if self.stage in ("expired", "closed"):
            return "TERMINATED"
        return "DRAFT"

    def to_dict(self) -> dict:
        signers = self.signers_json or []
        signed_cnt = sum(1 for s in signers if s.get("status") == "signed")
        c_status = self.canonical_status()
        return {
            "id": self.id,
            "document_id": self.document_id,
            "project_id": self.project_id,
            "template_id": self.template_id,
            "contract_number": self.contract_number or f"CTR-{self.document_id:04d}",
            "contract_type": self.contract_type or "msa",
            "contract_status": c_status,
            "contract_status_label": CONTRACT_STATUS_LABELS.get(c_status, "Draft"),
            "stage": self.stage,
            "stage_label": STAGE_LABELS.get(self.stage, "Draft"),
            "counterparty_name": self.counterparty_name or "",
            "deal_value": self.deal_value or "",
            "currency": self.currency or "USD",
            "effective_date": self.effective_date or "",
            "expiration_date": self.expiration_date or "",
            "governing_law": self.governing_law or "",
            "letterhead_id": self.letterhead_id,
            "stamp_id": self.stamp_id,
            "renewal_type": self.renewal_type or "none",
            "notice_period_days": self.notice_period_days if self.notice_period_days is not None else 30,
            "renewal_term_months": self.renewal_term_months,
            "routing_mode": self.routing_mode or "parallel",
            "edit_locked": bool(self.edit_locked or self.stage in LOCKED_STAGES or c_status != "DRAFT"),
            "evidence_retention_id": self.evidence_retention_id,
            "stamp_receipt_id": self.stamp_receipt_id,
            "parent_contract_id": self.parent_contract_id,
            "relationship_type": self.relationship_type or "",
            "checklist": self.checklist_json or {},
            "signers": signers,
            "signers_total": len(signers),
            "signers_signed": signed_cnt,
            "events": self.events_json or [],
            "closed_at": self.closed_at.strftime("%Y-%m-%d %H:%M UTC") if self.closed_at else "",
            "execution_sha256": self.execution_sha256 or "",
            "suspended_at": self.suspended_at.strftime("%Y-%m-%d %H:%M UTC") if self.suspended_at else "",
            "suspension_reason": self.suspension_reason or "",
            "expected_resume_date": self.expected_resume_date or "",
            "terminated_at": self.terminated_at.strftime("%Y-%m-%d %H:%M UTC") if self.terminated_at else "",
            "termination_type": self.termination_type or "",
            "termination_reason": self.termination_reason or "",
        }


class ContractKeyTerm(db.Model):
    """Structured key contractual terms (probation, SLA, financial, notice, liability)."""

    __tablename__ = "contract_key_terms"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    contract_id = db.Column(
        db.Integer, db.ForeignKey("contract_workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category = db.Column(db.String(32), nullable=False, default="custom")
    term_key = db.Column(db.String(64), nullable=True)
    label = db.Column(db.String(200), nullable=False)
    value_text = db.Column(db.String(300), nullable=False, default="")
    numeric_value = db.Column(db.Float, nullable=True)
    unit = db.Column(db.String(32), nullable=True)
    start_date = db.Column(db.String(32), nullable=True)
    end_date = db.Column(db.String(32), nullable=True)
    alert_days_before = db.Column(db.Integer, nullable=False, default=14)
    status = db.Column(db.String(24), nullable=False, default="active")
    clause_ref = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        days_remaining = None
        if self.end_date:
            try:
                end_dt = datetime.strptime(self.end_date[:10], "%Y-%m-%d").date()
                days_remaining = (end_dt - datetime.utcnow().date()).days
            except ValueError:
                pass
        return {
            "id": self.id,
            "contract_id": self.contract_id,
            "category": self.category or "custom",
            "term_key": self.term_key or "",
            "label": self.label,
            "value_text": self.value_text or "",
            "numeric_value": self.numeric_value,
            "unit": self.unit or "",
            "start_date": self.start_date or "",
            "end_date": self.end_date or "",
            "alert_days_before": self.alert_days_before,
            "days_remaining": days_remaining,
            "status": self.status or "active",
            "clause_ref": self.clause_ref or "",
            "notes": self.notes or "",
        }


class ContractDeliverable(db.Model):
    """Project-based deliverable, payment tranche, acceptance gate, or probation review."""

    __tablename__ = "contract_deliverables"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    contract_id = db.Column(
        db.Integer, db.ForeignKey("contract_workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    deliverable_type = db.Column(db.String(32), nullable=False, default="milestone")
    project_phase = db.Column(db.String(80), nullable=True)
    owner_name = db.Column(db.String(140), nullable=True)
    counterparty_owner = db.Column(db.String(140), nullable=True)
    due_date = db.Column(db.String(32), nullable=True)
    weight_pct = db.Column(db.Integer, nullable=False, default=10)
    payment_amount = db.Column(db.Float, nullable=True)
    acceptance_criteria = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(24), nullable=False, default="not_started")
    evidence_note = db.Column(db.String(500), nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    accepted_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "contract_id": self.contract_id,
            "title": self.title,
            "description": self.description or "",
            "deliverable_type": self.deliverable_type or "milestone",
            "project_phase": self.project_phase or "",
            "owner_name": self.owner_name or "",
            "counterparty_owner": self.counterparty_owner or "",
            "due_date": self.due_date or "",
            "weight_pct": self.weight_pct if self.weight_pct is not None else 10,
            "payment_amount": self.payment_amount,
            "acceptance_criteria": self.acceptance_criteria or "",
            "status": self.status or "not_started",
            "evidence_note": self.evidence_note or "",
            "accepted_at": self.accepted_at.strftime("%Y-%m-%d %H:%M UTC") if self.accepted_at else "",
        }


class ContractObligation(db.Model):
    """Post-execution obligation, payment milestone, or renewal deliverable."""

    __tablename__ = "contract_obligations"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    contract_id = db.Column(
        db.Integer, db.ForeignKey("contract_workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(32), nullable=False, default="deliverable")
    owner_name = db.Column(db.String(140), nullable=True)
    due_date = db.Column(db.String(32), nullable=True)
    status = db.Column(db.String(24), nullable=False, default="pending")
    notes = db.Column(db.String(500), nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "contract_id": self.contract_id,
            "title": self.title,
            "category": self.category,
            "owner_name": self.owner_name or "",
            "due_date": self.due_date or "",
            "status": self.status,
            "notes": self.notes or "",
            "completed_at": self.completed_at.strftime("%Y-%m-%d %H:%M UTC") if self.completed_at else "",
        }


_TABLE_READY = False

_WORKFLOW_MIGRATION_COLUMNS = (
    ("project_id", "INTEGER"),
    ("template_id", "INTEGER"),
    ("contract_status", "VARCHAR(20) NOT NULL DEFAULT 'DRAFT'"),
    ("contract_number", "VARCHAR(64)"),
    ("contract_type", "VARCHAR(48) NOT NULL DEFAULT 'msa'"),
    ("expiration_date", "VARCHAR(32)"),
    ("renewal_type", "VARCHAR(24) NOT NULL DEFAULT 'none'"),
    ("notice_period_days", "INTEGER NOT NULL DEFAULT 30"),
    ("renewal_term_months", "INTEGER"),
    ("routing_mode", "VARCHAR(24) NOT NULL DEFAULT 'parallel'"),
    ("edit_locked", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("evidence_retention_id", "INTEGER"),
    ("stamp_receipt_id", "INTEGER"),
    ("parent_contract_id", "INTEGER"),
    ("relationship_type", "VARCHAR(24)"),
    ("suspended_at", "TIMESTAMP"),
    ("suspension_reason", "VARCHAR(500)"),
    ("expected_resume_date", "VARCHAR(32)"),
    ("terminated_at", "TIMESTAMP"),
    ("termination_type", "VARCHAR(32)"),
    ("termination_reason", "VARCHAR(500)"),
)


def ensure_contract_workflow_table() -> None:
    """Create/upgrade all Contracts CLM tables idempotently."""
    global _TABLE_READY
    if _TABLE_READY:
        return
    try:
        insp = inspect(db.engine)
        for model in (
            Project,
            ContractTemplate,
            ContractWorkflow,
            ContractKeyTerm,
            ContractDeliverable,
            ContractObligation,
        ):
            if not insp.has_table(model.__tablename__):
                model.__table__.create(db.engine, checkfirst=True)
        existing = {c["name"] for c in insp.get_columns(ContractWorkflow.__tablename__)}
        with db.engine.begin() as conn:
            for col_name, col_ddl in _WORKFLOW_MIGRATION_COLUMNS:
                if col_name not in existing:
                    conn.execute(
                        text(f"ALTER TABLE {ContractWorkflow.__tablename__} ADD COLUMN {col_name} {col_ddl}")
                    )
        _TABLE_READY = True
    except Exception:
        pass
