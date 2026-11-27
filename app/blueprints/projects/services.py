"""Transactional domain services for TrustSeal Enterprise Project Management.

Covers:
- Audit & Transactional Outbox emission (PM-34)
- Decimal financial rollup & budget reconciliation (PM-15/16)
- WBS hierarchy cycle detection (PM-06)
- Task dependency DAG cycle detection (PM-07)
- Idempotent Intake-to-Project conversion (PM-01)
- Timesheet approval -> single immutable cost posting with rate snapshot (PM-13)
- Resource over-allocation capacity check (PM-12)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from flask import g

from app.extensions import db
from app.models.contract_workflow import Project
from app.models.event_delivery import OutboxEvent, SecurityEvent
from app.models.project_management import (
    ProjectBudgetLine,
    ProjectCostEvent,
    ProjectIntake,
    ProjectMembership,
    ProjectResourceAllocation,
    ProjectTask,
    ProjectTaskDependency,
    ProjectTimeEntry,
    ProjectWBSNode,
    to_decimal,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def emit_project_event(
    *,
    organization_id: int,
    actor_id: int | None,
    event_type: str,
    aggregate_type: str,
    aggregate_id: int,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> None:
    """Record a SecurityEvent and transactional OutboxEvent in the current DB transaction."""
    corr_id = getattr(g, "request_id", None) or uuid.uuid4().hex
    db.session.add(
        SecurityEvent(
            organization_id=organization_id,
            actor_id=actor_id,
            action=event_type[:100],
            resource_type=aggregate_type[:60],
            resource_id=aggregate_id,
            outcome="success",
            correlation_id=corr_id[:64],
        )
    )
    ikey = (idempotency_key or f"{event_type}:{aggregate_type}:{aggregate_id}:{uuid.uuid4().hex[:12]}")[:128]
    safe_payload = {
        "schema_version": "2.0",
        "organization_id": organization_id,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "actor_id": actor_id,
        "correlation_id": corr_id,
        "occurred_at": _utcnow().isoformat(),
        **(payload or {}),
    }
    db.session.add(
        OutboxEvent(
            event_type=event_type[:100],
            aggregate_type=aggregate_type[:60],
            aggregate_id=aggregate_id,
            organization_id=organization_id,
            payload=safe_payload,
            idempotency_key=ikey,
            state="pending",
        )
    )


def compute_project_financials(
    project: Project,
    budget_lines: list[ProjectBudgetLine] | None = None,
    cost_events: list[ProjectCostEvent] | None = None,
) -> dict[str, Any]:
    """Compute exact Decimal financial totals (zero float arithmetic).

    Rules (Spec Section 6):
    - Approved Budget = sum(budget_lines) if present else project.effective_budget_decimal()
    - Actuals = sum(posted/approved actuals) - sum(reversals)
    - Commitments = sum(posted/approved commitments)
    - Accruals = sum(posted/approved accruals)
    - Available Budget = Approved Budget - Actuals - Commitments
    """
    if budget_lines is None:
        budget_lines = ProjectBudgetLine.query.filter_by(
            organization_id=project.organization_id, project_id=project.id
        ).all()
    if cost_events is None:
        cost_events = ProjectCostEvent.query.filter_by(
            organization_id=project.organization_id, project_id=project.id
        ).all()

    lines_total = sum((Decimal(b.planned_amount or 0) for b in budget_lines), Decimal("0.00"))
    approved_budget = lines_total if lines_total > Decimal("0.00") else project.effective_budget_decimal()

    actuals = Decimal("0.00")
    commitments = Decimal("0.00")
    accruals = Decimal("0.00")
    for ev in cost_events:
        if ev.status not in ("approved", "posted"):
            continue
        amt = Decimal(ev.amount or 0)
        if ev.event_type == "actual":
            actuals += amt
        elif ev.event_type == "reversal":
            actuals -= abs(amt)
        elif ev.event_type == "commitment":
            commitments += amt
        elif ev.event_type == "accrual":
            accruals += amt

    total_exposure = actuals + commitments
    available_budget = approved_budget - total_exposure
    util_pct = (
        int(round((total_exposure / approved_budget) * Decimal("100")))
        if approved_budget > Decimal("0.00")
        else 0
    )

    return {
        "currency": project.currency or "USD",
        "approved_budget": approved_budget.quantize(Decimal("0.01")),
        "actuals": actuals.quantize(Decimal("0.01")),
        "commitments": commitments.quantize(Decimal("0.01")),
        "accruals": accruals.quantize(Decimal("0.01")),
        "total_exposure": total_exposure.quantize(Decimal("0.01")),
        "available_budget": available_budget.quantize(Decimal("0.01")),
        "budget_util_pct": util_pct,
        "approved_budget_str": str(approved_budget.quantize(Decimal("0.01"))),
        "actuals_str": str(actuals.quantize(Decimal("0.01"))),
        "commitments_str": str(commitments.quantize(Decimal("0.01"))),
        "accruals_str": str(accruals.quantize(Decimal("0.01"))),
        "available_budget_str": str(available_budget.quantize(Decimal("0.01"))),
    }


def wbs_would_cycle(project_id: int, node_id: int, proposed_parent_id: int | None) -> bool:
    """Return True if reparenting ``node_id`` under ``proposed_parent_id`` creates a cycle."""
    if proposed_parent_id is None:
        return False
    if node_id == proposed_parent_id:
        return True
    nodes = {
        n.id: n.parent_id
        for n in ProjectWBSNode.query.filter_by(project_id=project_id).all()
    }
    cur = proposed_parent_id
    visited = {node_id}
    while cur is not None:
        if cur in visited:
            return True
        visited.add(cur)
        cur = nodes.get(cur)
    return False


def dependency_would_cycle(project_id: int, predecessor_id: int, successor_id: int) -> bool:
    """Return True if adding edge predecessor -> successor creates a cycle in the task DAG."""
    if predecessor_id == successor_id:
        return True
    adj: dict[int, list[int]] = {}
    for dep in ProjectTaskDependency.query.filter_by(project_id=project_id).all():
        adj.setdefault(dep.predecessor_task_id, []).append(dep.successor_task_id)
    # Check if predecessor_id is reachable from successor_id
    stack = [successor_id]
    visited: set[int] = set()
    while stack:
        cur = stack.pop()
        if cur == predecessor_id:
            return True
        if cur in visited:
            continue
        visited.add(cur)
        stack.extend(adj.get(cur, []))
    return False


def count_overallocated_resources(organization_id: int, project_id: int) -> int:
    """Count distinct users on this project whose confirmed active allocations exceed 100%."""
    proj_allocs = ProjectResourceAllocation.query.filter_by(
        organization_id=organization_id, project_id=project_id, status="confirmed"
    ).all()
    user_ids = {a.user_id for a in proj_allocs if a.user_id is not None}
    if not user_ids:
        return sum(1 for a in proj_allocs if int(a.allocation_pct or 0) > 100)
    all_confirmed = ProjectResourceAllocation.query.filter(
        ProjectResourceAllocation.organization_id == organization_id,
        ProjectResourceAllocation.user_id.in_(user_ids),
        ProjectResourceAllocation.status == "confirmed",
    ).all()
    totals: dict[int, int] = {}
    for a in all_confirmed:
        totals[a.user_id] = totals.get(a.user_id, 0) + int(a.allocation_pct or 0)
    return sum(1 for pct in totals.values() if pct > 100)


def convert_intake_to_project(intake: ProjectIntake, actor) -> tuple[Project, bool]:
    """Idempotently convert an approved ProjectIntake into exactly one Project.

    Returns ``(project, created_now)``. Repeated calls return the existing linked project.
    """
    if intake.converted_project_id:
        existing = Project.query.filter_by(
            id=intake.converted_project_id, organization_id=intake.organization_id
        ).first()
        if existing is not None:
            return existing, False

    if intake.status != "approved":
        raise ValueError("Only approved intake requests can be converted to a project")

    cnt = Project.query.filter_by(organization_id=intake.organization_id).count()
    code = f"PRJ-{datetime.utcnow().year}-{cnt + 1:03d}"
    budget_dec = to_decimal(intake.estimated_budget) if intake.estimated_budget is not None else None
    proj = Project(
        organization_id=intake.organization_id,
        project_code=code,
        name=intake.title[:200],
        description=intake.problem_statement,
        category=intake.category or "client_delivery",
        delivery_methodology=intake.delivery_methodology or "hybrid",
        portfolio_id=intake.portfolio_id,
        programme_id=intake.programme_id,
        sponsor_user_id=intake.sponsor_user_id or actor.id,
        owner_user_id=actor.id,
        status="active",
        lifecycle_state="authorized",
        budget_amount=float(budget_dec) if budget_dec is not None else None,
        budget_numeric=budget_dec,
        currency=intake.currency or "USD",
        is_default=False,
    )
    db.session.add(proj)
    db.session.flush()

    intake.converted_project_id = proj.id
    # Seed project manager membership for creator
    db.session.add(
        ProjectMembership(
            organization_id=intake.organization_id,
            project_id=proj.id,
            user_id=actor.id,
            project_role="project_manager",
            can_view_finance=True,
            is_active=True,
            granted_by_id=actor.id,
        )
    )
    emit_project_event(
        organization_id=intake.organization_id,
        actor_id=actor.id,
        event_type="project.created",
        aggregate_type="project",
        aggregate_id=proj.id,
        payload={"source_intake_id": intake.id, "project_code": proj.project_code},
        idempotency_key=f"intake.converted:{intake.id}",
    )
    return proj, True


def approve_time_entry(entry: ProjectTimeEntry, project: Project, actor, hourly_rate: Decimal | None = None) -> ProjectCostEvent:
    """Approve a time entry once, snapshot its rate, update task actual_hours, and post one cost event."""
    if entry.status == "approved" and entry.posted_cost_event_id:
        existing_ev = db.session.get(ProjectCostEvent, entry.posted_cost_event_id)
        if existing_ev is not None:
            return existing_ev

    # Resolve effective rate from allocation if not explicitly passed
    rate = hourly_rate
    if rate is None:
        alloc = ProjectResourceAllocation.query.filter_by(
            organization_id=project.organization_id,
            project_id=project.id,
            user_id=entry.user_id,
        ).first()
        if alloc and alloc.hourly_cost_rate is not None:
            rate = Decimal(alloc.hourly_cost_rate)
        else:
            rate = Decimal("0.00")

    rate = rate.quantize(Decimal("0.01"))
    cost_amt = (Decimal(entry.hours) * rate).quantize(Decimal("0.01"))
    source_ref = f"timesheet:{entry.id}"

    existing = ProjectCostEvent.query.filter_by(
        organization_id=project.organization_id,
        project_id=project.id,
        source_ref=source_ref,
    ).first()
    if existing is None:
        ev = ProjectCostEvent(
            organization_id=project.organization_id,
            project_id=project.id,
            event_type="actual",
            category="labor",
            description=f"Approved timesheet #{entry.id} ({entry.hours}h @ {rate} {entry.currency})",
            amount=cost_amt,
            currency=entry.currency or project.currency or "USD",
            source_ref=source_ref,
            status="posted",
            event_date=entry.work_date,
            created_by_id=actor.id,
        )
        db.session.add(ev)
        db.session.flush()
    else:
        ev = existing

    entry.hourly_rate_snapshot = rate
    entry.cost_amount = cost_amt
    entry.status = "approved"
    entry.approved_by_id = actor.id
    entry.approved_at = _utcnow()
    entry.posted_cost_event_id = ev.id

    if entry.task_id:
        task = db.session.get(ProjectTask, entry.task_id)
        if task and task.project_id == project.id:
            task.actual_hours = (Decimal(task.actual_hours or 0) + Decimal(entry.hours)).quantize(Decimal("0.01"))

    emit_project_event(
        organization_id=project.organization_id,
        actor_id=actor.id,
        event_type="timesheet.approved",
        aggregate_type="project_time_entry",
        aggregate_id=entry.id,
        payload={"project_id": project.id, "hours": str(entry.hours), "cost_event_id": ev.id},
        idempotency_key=f"timesheet.approved:{entry.id}",
    )
    return ev
