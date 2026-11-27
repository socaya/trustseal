"""Enterprise Project, Programme, Portfolio & Resource Management models (v2.0).

Implements the data layer for TrustSeal Projects (`docs/TrustSeal_Enterprise_Project_Management_Module_Specification.md`):
- PM-01: ``ProjectIntake`` (demand & investment intake with idempotent 1-to-1 project conversion)
- PM-02: ``ProjectPortfolio`` (strategic portfolios with Decimal budget ceilings)
- PM-03: ``ProjectProgramme`` (multi-project programmes)
- PM-04: ``ProjectCharter`` & ``ProjectGate`` (versioned charter & stage-gate governance)
- PM-06: ``ProjectWBSNode`` (hierarchical Work Breakdown Structure with cycle protection)
- PM-07: ``ProjectTaskDependency`` (FS/SS/FF/SF dependencies with DAG cycle protection)
- PM-08: ``ProjectTask`` (identity-backed assignee, typed dates, effort hours, WBS link)
- PM-12: ``ProjectResourceAllocation`` (named allocations with FTE % and capacity checks)
- PM-13: ``ProjectTimeEntry`` (timesheets with rate snapshot & single cost posting on approval)
- PM-15/16: ``ProjectBudgetLine`` & ``ProjectCostEvent`` (PostgreSQL NUMERIC decimal money ledger)
- PM-19: ``ProjectRisk`` (full RAID register: risk, issue, assumption, dependency, P×I scoring)
- PM-20: ``ProjectChangeRequest`` (integrated change control with cost/schedule impact)
- PM-33: ``ProjectMembership`` (project-scoped role assignments & finance visibility)
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from app.extensions import db


LIFECYCLE_STATES = (
    "draft",
    "proposed",
    "assessing",
    "authorized",
    "planning",
    "mobilizing",
    "executing",
    "handing_over",
    "closing",
    "closed",
    "archived",
    "on_hold",
    "cancelled",
)

GATE_STAGES = (
    "idea_intake",
    "feasibility",
    "initiation",
    "planning",
    "mobilization",
    "execution",
    "acceptance_handover",
    "closure",
    "benefits_review",
)

GATE_STATES = ("not_ready", "submitted", "in_review", "approved", "rejected", "returned", "superseded")

DELIVERY_METHODOLOGIES = ("predictive", "agile", "hybrid")

TASK_STATUSES = ("todo", "in_progress", "review", "done", "blocked")
TASK_PRIORITIES = ("low", "medium", "high", "critical", "urgent")
DEPENDENCY_TYPES = ("FS", "SS", "FF", "SF")

RAID_ITEM_TYPES = ("risk", "issue", "assumption", "dependency")
RISK_CATEGORIES = ("contractual", "financial", "schedule", "compliance", "operational", "technical", "resource")
RISK_SEVERITIES = ("low", "medium", "high", "critical")
RISK_STATUSES = ("open", "mitigating", "mitigated", "escalated", "closed")

ALLOCATION_STATUSES = ("tentative", "confirmed", "released")
TIMESHEET_STATUSES = ("draft", "submitted", "approved", "returned", "rejected")
COST_EVENT_TYPES = ("commitment", "actual", "accrual", "reversal")
COST_EVENT_STATUSES = ("draft", "approved", "posted", "reversed")
CHANGE_TYPES = ("scope", "schedule", "budget", "resource", "requirement", "contract")
CHANGE_STATUSES = ("draft", "submitted", "in_review", "approved", "rejected", "implemented")
INTAKE_STATUSES = ("submitted", "assessing", "approved", "deferred", "rejected")

PROJECT_ROLES = (
    "sponsor",
    "pmo",
    "project_manager",
    "programme_manager",
    "resource_manager",
    "team_lead",
    "member",
    "finance",
    "procurement",
    "contract_legal",
    "qa_me",
    "viewer",
    "external_client",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso_date(val: Any) -> date | None:
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    s = str(val or "").strip()[:10]
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def to_decimal(val: Any, default: str = "0.00") -> Decimal:
    if val is None or val == "":
        return Decimal(default)
    if isinstance(val, Decimal):
        return val.quantize(Decimal("0.01"))
    try:
        cleaned = str(val).replace(",", "").strip()
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except Exception:
        return Decimal(default)


# =====================================================================
# PM-02 & PM-03: PORTFOLIOS & PROGRAMMES
# =====================================================================

class ProjectPortfolio(db.Model):
    __tablename__ = "project_portfolios"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    code = db.Column(db.String(40), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    strategic_objective = db.Column(db.String(300), nullable=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    budget_ceiling = db.Column(db.Numeric(18, 2), nullable=True)
    currency = db.Column(db.String(12), nullable=False, default="USD")
    status = db.Column(db.String(24), nullable=False, default="active")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        db.UniqueConstraint("organization_id", "code", name="uq_portfolio_org_code"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "description": self.description or "",
            "strategic_objective": self.strategic_objective or "",
            "owner_user_id": self.owner_user_id,
            "budget_ceiling": str(self.budget_ceiling) if self.budget_ceiling is not None else None,
            "currency": self.currency or "USD",
            "status": self.status or "active",
            "created_at": self.created_at.strftime("%Y-%m-%d") if self.created_at else "",
        }


class ProjectProgramme(db.Model):
    __tablename__ = "project_programmes"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey("project_portfolios.id"), nullable=True, index=True)
    code = db.Column(db.String(40), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    sponsor_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    manager_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    budget_ceiling = db.Column(db.Numeric(18, 2), nullable=True)
    currency = db.Column(db.String(12), nullable=False, default="USD")
    target_end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(24), nullable=False, default="active")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        db.UniqueConstraint("organization_id", "code", name="uq_programme_org_code"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "portfolio_id": self.portfolio_id,
            "code": self.code,
            "name": self.name,
            "description": self.description or "",
            "sponsor_user_id": self.sponsor_user_id,
            "manager_user_id": self.manager_user_id,
            "budget_ceiling": str(self.budget_ceiling) if self.budget_ceiling is not None else None,
            "currency": self.currency or "USD",
            "target_end_date": self.target_end_date.isoformat() if self.target_end_date else "",
            "status": self.status or "active",
            "created_at": self.created_at.strftime("%Y-%m-%d") if self.created_at else "",
        }


# =====================================================================
# PM-01: DEMAND & INVESTMENT INTAKE
# =====================================================================

class ProjectIntake(db.Model):
    __tablename__ = "project_intakes"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    intake_code = db.Column(db.String(40), nullable=False)
    title = db.Column(db.String(220), nullable=False)
    problem_statement = db.Column(db.Text, nullable=True)
    strategic_alignment = db.Column(db.String(240), nullable=True)
    category = db.Column(db.String(48), nullable=False, default="client_delivery")
    delivery_methodology = db.Column(db.String(24), nullable=False, default="hybrid")
    portfolio_id = db.Column(db.Integer, db.ForeignKey("project_portfolios.id"), nullable=True)
    programme_id = db.Column(db.Integer, db.ForeignKey("project_programmes.id"), nullable=True)
    sponsor_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    requester_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    estimated_budget = db.Column(db.Numeric(18, 2), nullable=True)
    currency = db.Column(db.String(12), nullable=False, default="USD")
    value_score = db.Column(db.Integer, nullable=False, default=3)        # 1..5
    urgency_score = db.Column(db.Integer, nullable=False, default=3)      # 1..5
    feasibility_score = db.Column(db.Integer, nullable=False, default=3)  # 1..5
    risk_score = db.Column(db.Integer, nullable=False, default=3)         # 1..5 (lower is safer)
    weighted_score = db.Column(db.Numeric(6, 2), nullable=False, default=Decimal("3.00"))
    status = db.Column(db.String(24), nullable=False, default="submitted", index=True)
    decision_rationale = db.Column(db.Text, nullable=True)
    decided_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    decided_at = db.Column(db.DateTime(timezone=True), nullable=True)
    converted_project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True, unique=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        db.UniqueConstraint("organization_id", "intake_code", name="uq_intake_org_code"),
    )

    def compute_weighted_score(self) -> Decimal:
        # Value 35%, Urgency 25%, Feasibility 25%, Inverse Risk 15%
        inv_risk = max(1, 6 - int(self.risk_score or 3))
        val = (
            Decimal(int(self.value_score or 3)) * Decimal("0.35")
            + Decimal(int(self.urgency_score or 3)) * Decimal("0.25")
            + Decimal(int(self.feasibility_score or 3)) * Decimal("0.25")
            + Decimal(inv_risk) * Decimal("0.15")
        )
        return val.quantize(Decimal("0.01"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "intake_code": self.intake_code,
            "title": self.title,
            "problem_statement": self.problem_statement or "",
            "strategic_alignment": self.strategic_alignment or "",
            "category": self.category or "client_delivery",
            "delivery_methodology": self.delivery_methodology or "hybrid",
            "portfolio_id": self.portfolio_id,
            "programme_id": self.programme_id,
            "sponsor_user_id": self.sponsor_user_id,
            "requester_user_id": self.requester_user_id,
            "estimated_budget": str(self.estimated_budget) if self.estimated_budget is not None else None,
            "currency": self.currency or "USD",
            "value_score": int(self.value_score or 3),
            "urgency_score": int(self.urgency_score or 3),
            "feasibility_score": int(self.feasibility_score or 3),
            "risk_score": int(self.risk_score or 3),
            "weighted_score": str(self.weighted_score or Decimal("3.00")),
            "status": self.status or "submitted",
            "decision_rationale": self.decision_rationale or "",
            "converted_project_id": self.converted_project_id,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
        }


# =====================================================================
# PM-04: PROJECT CHARTER & STAGE GATES
# =====================================================================

class ProjectCharter(db.Model):
    __tablename__ = "project_charters"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    objectives = db.Column(db.Text, nullable=True)
    scope_in = db.Column(db.Text, nullable=True)
    scope_out = db.Column(db.Text, nullable=True)
    success_criteria = db.Column(db.Text, nullable=True)
    cost_tolerance_pct = db.Column(db.Numeric(5, 2), nullable=False, default=Decimal("10.00"))
    schedule_tolerance_days = db.Column(db.Integer, nullable=False, default=14)
    status = db.Column(db.String(24), nullable=False, default="draft")  # draft, approved, superseded
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "version": int(self.version or 1),
            "objectives": self.objectives or "",
            "scope_in": self.scope_in or "",
            "scope_out": self.scope_out or "",
            "success_criteria": self.success_criteria or "",
            "cost_tolerance_pct": str(self.cost_tolerance_pct or Decimal("10.00")),
            "schedule_tolerance_days": int(self.schedule_tolerance_days or 14),
            "status": self.status or "draft",
            "approved_by_id": self.approved_by_id,
            "approved_at": self.approved_at.strftime("%Y-%m-%d %H:%M UTC") if self.approved_at else "",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
        }


class ProjectGate(db.Model):
    __tablename__ = "project_gates"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    stage = db.Column(db.String(32), nullable=False)
    gate_state = db.Column(db.String(24), nullable=False, default="not_ready")
    decision_note = db.Column(db.Text, nullable=True)
    waiver_reason = db.Column(db.Text, nullable=True)
    waiver_expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    evidence_snapshot_json = db.Column(db.JSON, nullable=False, default=dict)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    decided_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    decided_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        db.UniqueConstraint("project_id", "stage", name="uq_project_gate_stage"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "stage": self.stage,
            "gate_state": self.gate_state or "not_ready",
            "decision_note": self.decision_note or "",
            "waiver_reason": self.waiver_reason or "",
            "waiver_expires_at": self.waiver_expires_at.isoformat() if self.waiver_expires_at else "",
            "evidence_snapshot": self.evidence_snapshot_json or {},
            "decided_by_id": self.decided_by_id,
            "decided_at": self.decided_at.strftime("%Y-%m-%d %H:%M UTC") if self.decided_at else "",
        }


# =====================================================================
# PM-06: WORK BREAKDOWN STRUCTURE (WBS)
# =====================================================================

class ProjectWBSNode(db.Model):
    __tablename__ = "project_wbs_nodes"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("project_wbs_nodes.id"), nullable=True, index=True)
    wbs_code = db.Column(db.String(32), nullable=False)
    title = db.Column(db.String(220), nullable=False)
    node_type = db.Column(db.String(24), nullable=False, default="work_package")  # phase, workstream, work_package
    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    budget_allocation = db.Column(db.Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    weight_pct = db.Column(db.Integer, nullable=False, default=0)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        db.CheckConstraint("weight_pct >= 0 AND weight_pct <= 100", name="ck_wbs_weight_pct"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "parent_id": self.parent_id,
            "wbs_code": self.wbs_code,
            "title": self.title,
            "node_type": self.node_type or "work_package",
            "owner_user_id": self.owner_user_id,
            "budget_allocation": str(self.budget_allocation or Decimal("0.00")),
            "weight_pct": int(self.weight_pct or 0),
            "sort_order": int(self.sort_order or 0),
        }


# =====================================================================
# PM-08 & PM-07: TASKS & SCHEDULE DEPENDENCIES
# =====================================================================

class ProjectTask(db.Model):
    """Execution task within a Project, optionally tied to a WBS node and/or TSD Contract."""

    __tablename__ = "project_tasks"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    project_id = db.Column(
        db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True
    )
    wbs_node_id = db.Column(
        db.Integer, db.ForeignKey("project_wbs_nodes.id"), nullable=True, index=True
    )
    parent_task_id = db.Column(
        db.Integer, db.ForeignKey("project_tasks.id"), nullable=True, index=True
    )
    contract_id = db.Column(
        db.Integer, db.ForeignKey("contract_workflows.id"), nullable=True, index=True
    )
    title = db.Column(db.String(220), nullable=False)
    description = db.Column(db.Text, nullable=True)
    phase = db.Column(db.String(64), nullable=True, default="Execution")
    assignee_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    assignee_name = db.Column(db.String(120), nullable=True)
    priority = db.Column(db.String(16), nullable=False, default="medium")
    status = db.Column(db.String(24), nullable=False, default="todo")
    start_date_typed = db.Column(db.Date, nullable=True)
    due_date = db.Column(db.String(32), nullable=True)
    due_date_typed = db.Column(db.Date, nullable=True)
    planned_hours = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    actual_hours = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    remaining_hours = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    is_milestone = db.Column(db.Boolean, nullable=False, default=False)
    progress_pct = db.Column(db.Integer, nullable=False, default=0)
    version = db.Column(db.Integer, nullable=False, default=1)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def effective_due_date(self) -> date | None:
        return self.due_date_typed or parse_iso_date(self.due_date)

    def to_dict(self) -> dict[str, Any]:
        due_d = self.effective_due_date()
        return {
            "id": self.id,
            "project_id": self.project_id,
            "wbs_node_id": self.wbs_node_id,
            "parent_task_id": self.parent_task_id,
            "contract_id": self.contract_id,
            "linked_document_id": self.contract_id,
            "title": self.title,
            "description": self.description or "",
            "phase": self.phase or "Execution",
            "assignee_user_id": self.assignee_user_id,
            "assignee_name": self.assignee_name or "",
            "priority": self.priority or "medium",
            "status": self.status or "todo",
            "start_date": self.start_date_typed.isoformat() if self.start_date_typed else "",
            "due_date": due_d.isoformat() if due_d else (self.due_date or ""),
            "planned_hours": str(self.planned_hours or Decimal("0.00")),
            "actual_hours": str(self.actual_hours or Decimal("0.00")),
            "remaining_hours": str(self.remaining_hours or Decimal("0.00")),
            "is_milestone": bool(self.is_milestone),
            "progress_pct": int(self.progress_pct or 0),
            "version": int(self.version or 1),
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
        }


class ProjectTaskDependency(db.Model):
    __tablename__ = "project_task_dependencies"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    predecessor_task_id = db.Column(db.Integer, db.ForeignKey("project_tasks.id"), nullable=False, index=True)
    successor_task_id = db.Column(db.Integer, db.ForeignKey("project_tasks.id"), nullable=False, index=True)
    dependency_type = db.Column(db.String(4), nullable=False, default="FS")  # FS, SS, FF, SF
    lag_days = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        db.UniqueConstraint("predecessor_task_id", "successor_task_id", name="uq_task_dep_pair"),
        db.CheckConstraint("predecessor_task_id != successor_task_id", name="ck_task_dep_no_self"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "predecessor_task_id": self.predecessor_task_id,
            "successor_task_id": self.successor_task_id,
            "dependency_type": self.dependency_type or "FS",
            "lag_days": int(self.lag_days or 0),
        }


# =====================================================================
# PM-12 & PM-13: RESOURCE ALLOCATIONS & TIMESHEETS
# =====================================================================

class ProjectResourceAllocation(db.Model):
    __tablename__ = "project_resource_allocations"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    resource_name = db.Column(db.String(160), nullable=False)
    role_title = db.Column(db.String(120), nullable=False, default="Contributor")
    allocation_pct = db.Column(db.Integer, nullable=False, default=50)
    planned_hours = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    hourly_cost_rate = db.Column(db.Numeric(12, 2), nullable=True)
    currency = db.Column(db.String(12), nullable=False, default="USD")
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(24), nullable=False, default="confirmed")  # tentative, confirmed, released
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        db.CheckConstraint("allocation_pct >= 1 AND allocation_pct <= 200", name="ck_alloc_pct_range"),
    )

    def to_dict(self, include_rates: bool = False) -> dict[str, Any]:
        out = {
            "id": self.id,
            "project_id": self.project_id,
            "user_id": self.user_id,
            "resource_name": self.resource_name,
            "role_title": self.role_title or "Contributor",
            "allocation_pct": int(self.allocation_pct or 0),
            "planned_hours": str(self.planned_hours or Decimal("0.00")),
            "currency": self.currency or "USD",
            "start_date": self.start_date.isoformat() if self.start_date else "",
            "end_date": self.end_date.isoformat() if self.end_date else "",
            "status": self.status or "confirmed",
        }
        if include_rates:
            out["hourly_cost_rate"] = str(self.hourly_cost_rate) if self.hourly_cost_rate is not None else None
        return out


class ProjectTimeEntry(db.Model):
    __tablename__ = "project_time_entries"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    wbs_node_id = db.Column(db.Integer, db.ForeignKey("project_wbs_nodes.id"), nullable=True)
    task_id = db.Column(db.Integer, db.ForeignKey("project_tasks.id"), nullable=True, index=True)
    contract_id = db.Column(db.Integer, db.ForeignKey("contract_workflows.id"), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    work_date = db.Column(db.Date, nullable=False, index=True)
    hours = db.Column(db.Numeric(8, 2), nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False, default=0)
    billable = db.Column(db.Boolean, nullable=False, default=True)
    cost_code = db.Column(db.String(48), nullable=True)
    notes = db.Column(db.String(400), nullable=True)
    return_reason = db.Column(db.String(400), nullable=True)
    hourly_rate_snapshot = db.Column(db.Numeric(12, 2), nullable=True)
    billing_rate_snapshot = db.Column(db.Numeric(12, 2), nullable=True)
    cost_amount = db.Column(db.Numeric(18, 2), nullable=True)
    billable_amount = db.Column(db.Numeric(18, 2), nullable=True)
    currency = db.Column(db.String(12), nullable=False, default="USD")
    status = db.Column(db.String(24), nullable=False, default="draft", index=True)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    locked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    posted_cost_event_id = db.Column(db.Integer, db.ForeignKey("project_cost_events.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        db.CheckConstraint("hours > 0 AND hours <= 24", name="ck_time_entry_hours"),
    )

    def to_dict(self, include_rates: bool = False) -> dict[str, Any]:
        out = {
            "id": self.id,
            "project_id": self.project_id,
            "wbs_node_id": self.wbs_node_id,
            "task_id": self.task_id,
            "contract_id": self.contract_id,
            "user_id": self.user_id,
            "work_date": self.work_date.isoformat() if self.work_date else "",
            "hours": str(self.hours or Decimal("0.00")),
            "duration_minutes": int(self.duration_minutes or int(Decimal(self.hours or 0) * 60)),
            "billable": bool(self.billable),
            "cost_code": self.cost_code or "",
            "notes": self.notes or "",
            "return_reason": self.return_reason or "",
            "currency": self.currency or "USD",
            "status": self.status or "draft",
            "approved_by_id": self.approved_by_id,
            "approved_at": self.approved_at.strftime("%Y-%m-%d %H:%M UTC") if self.approved_at else "",
            "locked": self.locked_at is not None,
            "posted_cost_event_id": self.posted_cost_event_id,
        }
        if include_rates:
            out["hourly_rate_snapshot"] = str(self.hourly_rate_snapshot) if self.hourly_rate_snapshot is not None else None
            out["billing_rate_snapshot"] = str(self.billing_rate_snapshot) if self.billing_rate_snapshot is not None else None
            out["cost_amount"] = str(self.cost_amount) if self.cost_amount is not None else None
            out["billable_amount"] = str(self.billable_amount) if self.billable_amount is not None else None
        return out


class ProjectTimeAdjustment(db.Model):
    """Immutable correction/reversal linked to an approved ProjectTimeEntry (PM-13.08)."""

    __tablename__ = "project_time_adjustments"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    original_entry_id = db.Column(db.Integer, db.ForeignKey("project_time_entries.id"), nullable=False, index=True)
    delta_hours = db.Column(db.Numeric(8, 2), nullable=False)
    delta_cost_amount = db.Column(db.Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    reason = db.Column(db.String(400), nullable=False)
    posted_cost_event_id = db.Column(db.Integer, db.ForeignKey("project_cost_events.id"), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "original_entry_id": self.original_entry_id,
            "delta_hours": str(self.delta_hours),
            "delta_cost_amount": str(self.delta_cost_amount),
            "reason": self.reason,
            "posted_cost_event_id": self.posted_cost_event_id,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M UTC") if self.created_at else "",
        }


# =====================================================================
# PM-15 & PM-16: DECIMAL BUDGETING & COST LEDGER
# =====================================================================

class ProjectBudgetLine(db.Model):
    __tablename__ = "project_budget_lines"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    wbs_node_id = db.Column(db.Integer, db.ForeignKey("project_wbs_nodes.id"), nullable=True, index=True)
    category = db.Column(db.String(48), nullable=False, default="labor")  # labor, vendor, equipment, materials, travel, overhead, contingency
    description = db.Column(db.String(240), nullable=False)
    planned_amount = db.Column(db.Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    currency = db.Column(db.String(12), nullable=False, default="USD")
    baseline_version = db.Column(db.Integer, nullable=False, default=1)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        db.CheckConstraint("planned_amount >= 0", name="ck_budget_line_nonneg"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "wbs_node_id": self.wbs_node_id,
            "category": self.category or "labor",
            "description": self.description,
            "planned_amount": str(self.planned_amount or Decimal("0.00")),
            "currency": self.currency or "USD",
            "baseline_version": int(self.baseline_version or 1),
        }


class ProjectCostEvent(db.Model):
    __tablename__ = "project_cost_events"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    wbs_node_id = db.Column(db.Integer, db.ForeignKey("project_wbs_nodes.id"), nullable=True, index=True)
    event_type = db.Column(db.String(24), nullable=False, default="actual")  # commitment, actual, accrual, reversal
    category = db.Column(db.String(48), nullable=False, default="labor")
    description = db.Column(db.String(240), nullable=False)
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    currency = db.Column(db.String(12), nullable=False, default="USD")
    source_ref = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(24), nullable=False, default="posted")  # draft, approved, posted, reversed
    event_date = db.Column(db.Date, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        db.UniqueConstraint("organization_id", "project_id", "source_ref", name="uq_cost_event_source_ref"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "wbs_node_id": self.wbs_node_id,
            "event_type": self.event_type or "actual",
            "category": self.category or "labor",
            "description": self.description,
            "amount": str(self.amount or Decimal("0.00")),
            "currency": self.currency or "USD",
            "source_ref": self.source_ref or "",
            "status": self.status or "posted",
            "event_date": self.event_date.isoformat() if self.event_date else "",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
        }


# =====================================================================
# PM-19 & PM-20: RAID REGISTER & INTEGRATED CHANGE CONTROL
# =====================================================================

class ProjectRisk(db.Model):
    """Structured RAID record (Risk, Issue, Assumption, Dependency) within a Project."""

    __tablename__ = "project_risks"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    project_id = db.Column(
        db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True
    )
    contract_id = db.Column(
        db.Integer, db.ForeignKey("contract_workflows.id"), nullable=True, index=True
    )
    item_type = db.Column(db.String(24), nullable=False, default="risk", index=True)
    title = db.Column(db.String(220), nullable=False)
    category = db.Column(db.String(32), nullable=False, default="contractual")
    severity = db.Column(db.String(16), nullable=False, default="medium")
    likelihood = db.Column(db.String(16), nullable=False, default="medium")
    probability_score = db.Column(db.Integer, nullable=False, default=3)  # 1..5
    impact_score = db.Column(db.Integer, nullable=False, default=3)       # 1..5
    exposure_amount = db.Column(db.Numeric(18, 2), nullable=True)
    mitigation_plan = db.Column(db.Text, nullable=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    owner_name = db.Column(db.String(120), nullable=True)
    due_date_typed = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(24), nullable=False, default="open")
    version = db.Column(db.Integer, nullable=False, default=1)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def rating_score(self) -> int:
        return int(self.probability_score or 3) * int(self.impact_score or 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "contract_id": self.contract_id,
            "item_type": self.item_type or "risk",
            "title": self.title,
            "category": self.category or "contractual",
            "severity": self.severity or "medium",
            "likelihood": self.likelihood or "medium",
            "probability_score": int(self.probability_score or 3),
            "impact_score": int(self.impact_score or 3),
            "rating_score": self.rating_score(),
            "exposure_amount": str(self.exposure_amount) if self.exposure_amount is not None else None,
            "mitigation_plan": self.mitigation_plan or "",
            "owner_user_id": self.owner_user_id,
            "owner_name": self.owner_name or "",
            "due_date": self.due_date_typed.isoformat() if self.due_date_typed else "",
            "status": self.status or "open",
            "version": int(self.version or 1),
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
        }


class ProjectChangeRequest(db.Model):
    __tablename__ = "project_change_requests"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    cr_number = db.Column(db.String(40), nullable=False)
    title = db.Column(db.String(220), nullable=False)
    change_type = db.Column(db.String(24), nullable=False, default="scope")
    rationale = db.Column(db.Text, nullable=True)
    cost_impact = db.Column(db.Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    schedule_impact_days = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(24), nullable=False, default="submitted", index=True)
    decision_note = db.Column(db.Text, nullable=True)
    requested_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    decided_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    decided_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        db.UniqueConstraint("project_id", "cr_number", name="uq_project_cr_number"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "cr_number": self.cr_number,
            "title": self.title,
            "change_type": self.change_type or "scope",
            "rationale": self.rationale or "",
            "cost_impact": str(self.cost_impact or Decimal("0.00")),
            "schedule_impact_days": int(self.schedule_impact_days or 0),
            "status": self.status or "submitted",
            "decision_note": self.decision_note or "",
            "requested_by_id": self.requested_by_id,
            "decided_by_id": self.decided_by_id,
            "decided_at": self.decided_at.strftime("%Y-%m-%d %H:%M UTC") if self.decided_at else "",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
        }


# =====================================================================
# PM-33: PROJECT-SCOPED MEMBERSHIP & ACCESS GOVERNANCE
# =====================================================================

class ProjectMembership(db.Model):
    __tablename__ = "project_memberships"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    project_role = db.Column(db.String(32), nullable=False, default="member")
    can_view_finance = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    granted_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        db.UniqueConstraint("project_id", "user_id", name="uq_project_member_user"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "user_id": self.user_id,
            "project_role": self.project_role or "member",
            "can_view_finance": bool(self.can_view_finance),
            "is_active": bool(self.is_active),
            "created_at": self.created_at.strftime("%Y-%m-%d") if self.created_at else "",
        }


def ensure_project_management_tables() -> None:
    """Backward-compatible helper. Production schema is managed by Alembic migration b2c3d4e5f604."""
    pass


def compute_project_health(
    *,
    budget_util_pct: int = 0,
    suspended_contracts: int = 0,
    tasks: list[ProjectTask] | None = None,
    risks: list[ProjectRisk] | None = None,
    available_budget: Decimal | None = None,
    approved_budget: Decimal | None = None,
    overallocated_resources: int = 0,
    today: date | None = None,
) -> dict[str, Any]:
    """Delegate to versioned explainable Health Policy v2.0."""
    from app.blueprints.projects.health_policy import evaluate_project_health

    return evaluate_project_health(
        budget_util_pct=budget_util_pct,
        suspended_contracts=suspended_contracts,
        tasks=tasks or [],
        risks=risks or [],
        available_budget=available_budget,
        approved_budget=approved_budget,
        overallocated_resources=overallocated_resources,
        today=today,
    )
