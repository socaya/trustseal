"""Project Management Module models (Tasks & Risks) aligned to TSD Contracts.

Extends ``Project`` and ``ContractWorkflow`` with first-class:
- ``ProjectTask``: Actionable workstream tasks optionally linked to a TSD Contract.
- ``ProjectRisk``: RAID / Risk & Issues register optionally linked to a TSD Contract.
- ``compute_project_health``: Deterministic RAG health scoring across budget,
  deliverables, tasks, contracts, and open risks.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.extensions import db


TASK_STATUSES = ("todo", "in_progress", "review", "done", "blocked")
TASK_PRIORITIES = ("low", "medium", "high", "critical")
RISK_CATEGORIES = ("contractual", "financial", "schedule", "compliance", "operational")
RISK_SEVERITIES = ("low", "medium", "high", "critical")
RISK_STATUSES = ("open", "mitigating", "closed")


class ProjectTask(db.Model):
    """Execution task within a Project, optionally tied to a TSD Contract."""

    __tablename__ = "project_tasks"

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
    title = db.Column(db.String(220), nullable=False)
    description = db.Column(db.Text, nullable=True)
    phase = db.Column(db.String(64), nullable=True, default="Execution")
    assignee_name = db.Column(db.String(120), nullable=True)
    priority = db.Column(db.String(16), nullable=False, default="medium")
    status = db.Column(db.String(24), nullable=False, default="todo")
    due_date = db.Column(db.String(32), nullable=True)
    progress_pct = db.Column(db.Integer, nullable=False, default=0)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "contract_id": self.contract_id,
            "title": self.title,
            "description": self.description or "",
            "phase": self.phase or "Execution",
            "assignee_name": self.assignee_name or "",
            "priority": self.priority or "medium",
            "status": self.status or "todo",
            "due_date": self.due_date or "",
            "progress_pct": int(self.progress_pct or 0),
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
        }


class ProjectRisk(db.Model):
    """RAID Risk & Issue record within a Project, optionally linked to a TSD Contract."""

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
    title = db.Column(db.String(220), nullable=False)
    category = db.Column(db.String(32), nullable=False, default="contractual")
    severity = db.Column(db.String(16), nullable=False, default="medium")
    likelihood = db.Column(db.String(16), nullable=False, default="medium")
    mitigation_plan = db.Column(db.Text, nullable=True)
    owner_name = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(24), nullable=False, default="open")
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "contract_id": self.contract_id,
            "title": self.title,
            "category": self.category or "contractual",
            "severity": self.severity or "medium",
            "likelihood": self.likelihood or "medium",
            "mitigation_plan": self.mitigation_plan or "",
            "owner_name": self.owner_name or "",
            "status": self.status or "open",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
        }


def ensure_project_management_tables() -> None:
    """Idempotently create project_tasks and project_risks tables if missing."""
    try:
        db.create_all()
    except Exception:
        pass


def compute_project_health(
    *,
    budget_util_pct: int = 0,
    suspended_contracts: int = 0,
    tasks: list[ProjectTask] | None = None,
    risks: list[ProjectRisk] | None = None,
) -> dict[str, Any]:
    """Compute RAG health status & 0–100 health score for a Project."""
    tasks = tasks or []
    risks = risks or []
    open_risks = [r for r in risks if (r.status or "open") != "closed"]
    crit_risks = sum(1 for r in open_risks if (r.severity or "") == "critical")
    high_risks = sum(1 for r in open_risks if (r.severity or "") == "high")
    blocked_tasks = sum(1 for t in tasks if (t.status or "") == "blocked")

    score = 100
    score -= crit_risks * 28
    score -= high_risks * 14
    score -= blocked_tasks * 10
    score -= suspended_contracts * 12
    if budget_util_pct > 100:
        score -= 25
    elif budget_util_pct >= 85:
        score -= 10
    score = max(15, min(100, score))

    if crit_risks > 0 or budget_util_pct > 100 or score < 60:
        rag, label = "critical", "Critical"
    elif high_risks > 0 or suspended_contracts > 0 or blocked_tasks > 0 or budget_util_pct >= 85 or score < 82:
        rag, label = "at_risk", "At Risk"
    else:
        rag, label = "on_track", "On Track"

    return {
        "score": score,
        "rag": rag,
        "label": label,
        "open_risks": len(open_risks),
        "critical_risks": crit_risks,
        "blocked_tasks": blocked_tasks,
    }
