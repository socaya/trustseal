"""Versioned, explainable multi-dimensional Project Health Policy (v2.0).

Implements Section 6 of the TrustSeal Enterprise Project Management Specification:
- Evaluates 6 explicit dimensions: ``schedule``, ``cost``, ``scope_delivery``,
  ``risk``, ``resource``, and ``contract``.
- Worst mandatory dimension determines overall RAG (``critical`` > ``at_risk`` > ``on_track``).
- Unknown / unconfigured inputs are surfaced explicitly as ``unknown`` rather than
  silently producing ``on_track``.
- Returns deterministic reasons, score (0–100), policy version, and per-dimension
  breakdowns for UI display and regression testing.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

POLICY_VERSION = "2.0.0"

_SEVERITY_RANK = {"unknown": 0, "on_track": 1, "at_risk": 2, "critical": 3}
_LABELS = {
    "on_track": "On Track",
    "at_risk": "At Risk",
    "critical": "Critical",
    "unknown": "Not Rated",
}


def evaluate_project_health(
    *,
    budget_util_pct: int = 0,
    suspended_contracts: int = 0,
    tasks: list[Any] | None = None,
    risks: list[Any] | None = None,
    available_budget: Decimal | None = None,
    approved_budget: Decimal | None = None,
    overallocated_resources: int = 0,
    today: date | None = None,
) -> dict[str, Any]:
    tasks = tasks or []
    risks = risks or []
    today = today or date.today()

    reasons: list[str] = []
    dimensions: dict[str, dict[str, Any]] = {}

    # 1. Schedule dimension (overdue tasks)
    open_tasks = [t for t in tasks if (getattr(t, "status", "") or "todo") != "done"]
    overdue_tasks = 0
    for t in open_tasks:
        due_d = t.effective_due_date() if hasattr(t, "effective_due_date") else None
        if due_d and due_d < today:
            overdue_tasks += 1
    if overdue_tasks >= 3:
        sched_rag = "critical"
        sched_reason = f"{overdue_tasks} overdue open tasks exceed threshold"
        reasons.append(sched_reason)
    elif overdue_tasks > 0:
        sched_rag = "at_risk"
        sched_reason = f"{overdue_tasks} overdue open task(s)"
        reasons.append(sched_reason)
    elif tasks:
        sched_rag = "on_track"
        sched_reason = "All scheduled tasks within due dates"
    else:
        sched_rag = "unknown"
        sched_reason = "No scheduled tasks tracked yet"
    dimensions["schedule"] = {
        "rag": sched_rag,
        "label": _LABELS[sched_rag],
        "overdue_tasks": overdue_tasks,
        "reason": sched_reason,
    }

    # 2. Cost dimension (Decimal budget ceiling & utilization)
    if approved_budget is not None and approved_budget > Decimal("0.00"):
        eff_avail = available_budget if available_budget is not None else approved_budget
        used = approved_budget - eff_avail
        pct = int(round((used / approved_budget) * Decimal("100")))
    else:
        pct = int(budget_util_pct or 0)

    if (available_budget is not None and available_budget < Decimal("0.00")) or pct > 100:
        cost_rag = "critical"
        cost_reason = f"Spend exceeds approved budget ({pct}%)"
        reasons.append(cost_reason)
    elif pct >= 85:
        cost_rag = "at_risk"
        cost_reason = f"Budget utilization at {pct}% (>= 85% warning threshold)"
        reasons.append(cost_reason)
    elif (approved_budget is not None and approved_budget > Decimal("0.00")) or pct > 0:
        cost_rag = "on_track"
        cost_reason = f"Budget utilization healthy ({pct}%)"
    else:
        cost_rag = "unknown"
        cost_reason = "No approved budget baseline configured"
    dimensions["cost"] = {
        "rag": cost_rag,
        "label": _LABELS[cost_rag],
        "utilization_pct": pct,
        "reason": cost_reason,
    }

    # 3. Scope / Delivery dimension (blocked tasks)
    blocked_tasks = sum(1 for t in tasks if (getattr(t, "status", "") or "") == "blocked")
    if blocked_tasks >= 3:
        scope_rag = "critical"
        scope_reason = f"{blocked_tasks} blocked work items"
        reasons.append(scope_reason)
    elif blocked_tasks > 0:
        scope_rag = "at_risk"
        scope_reason = f"{blocked_tasks} blocked work item(s)"
        reasons.append(scope_reason)
    elif tasks:
        scope_rag = "on_track"
        scope_reason = "Zero blocked tasks"
    else:
        scope_rag = "unknown"
        scope_reason = "No tasks tracked yet"
    dimensions["scope_delivery"] = {
        "rag": scope_rag,
        "label": _LABELS[scope_rag],
        "blocked_tasks": blocked_tasks,
        "reason": scope_reason,
    }

    # 4. Risk / RAID dimension
    open_risks = [
        r for r in risks if (getattr(r, "status", "open") or "open") not in ("closed", "mitigated")
    ]
    crit_risks = sum(
        1
        for r in open_risks
        if (getattr(r, "severity", "") or "") == "critical"
        or (hasattr(r, "rating_score") and r.rating_score() >= 20)
    )
    high_risks = sum(
        1
        for r in open_risks
        if (getattr(r, "severity", "") or "") == "high"
        and not (hasattr(r, "rating_score") and r.rating_score() >= 20)
    )
    if crit_risks > 0:
        risk_rag = "critical"
        risk_reason = f"{crit_risks} critical open RAID item(s)"
        reasons.append(risk_reason)
    elif high_risks > 0:
        risk_rag = "at_risk"
        risk_reason = f"{high_risks} high-severity open RAID item(s)"
        reasons.append(risk_reason)
    else:
        risk_rag = "on_track"
        risk_reason = "No high/critical open RAID exposure"
    dimensions["risk"] = {
        "rag": risk_rag,
        "label": _LABELS[risk_rag],
        "open_risks": len(open_risks),
        "critical_risks": crit_risks,
        "high_risks": high_risks,
        "reason": risk_reason,
    }

    # 5. Resource capacity dimension
    if overallocated_resources >= 2:
        res_rag = "critical"
        res_reason = f"{overallocated_resources} overallocated resource assignments (>100%)"
        reasons.append(res_reason)
    elif overallocated_resources == 1:
        res_rag = "at_risk"
        res_reason = "1 overallocated resource assignment (>100%)"
        reasons.append(res_reason)
    else:
        res_rag = "on_track"
        res_reason = "Resource allocations within capacity"
    dimensions["resource"] = {
        "rag": res_rag,
        "label": _LABELS[res_rag],
        "overallocated": overallocated_resources,
        "reason": res_reason,
    }

    # 6. Contract dimension
    if suspended_contracts >= 2:
        ctr_rag = "critical"
        ctr_reason = f"{suspended_contracts} suspended linked contracts"
        reasons.append(ctr_reason)
    elif suspended_contracts == 1:
        ctr_rag = "at_risk"
        ctr_reason = "1 suspended linked contract"
        reasons.append(ctr_reason)
    else:
        ctr_rag = "on_track"
        ctr_reason = "No suspended contracts"
    dimensions["contract"] = {
        "rag": ctr_rag,
        "label": _LABELS[ctr_rag],
        "suspended_contracts": suspended_contracts,
        "reason": ctr_reason,
    }

    # Numeric health score (0-100) + worst mandatory dimension wins
    score = 100
    score -= crit_risks * 28
    score -= high_risks * 14
    score -= blocked_tasks * 10
    score -= overdue_tasks * 8
    score -= suspended_contracts * 12
    score -= overallocated_resources * 12
    if pct > 100:
        score -= 25
    elif pct >= 85:
        score -= 10
    score = max(10, min(100, score))

    worst_rank = max(_SEVERITY_RANK[d["rag"]] for d in dimensions.values())
    if worst_rank == 3 or score < 60:
        overall_rag = "critical"
    elif worst_rank == 2 or score < 82:
        overall_rag = "at_risk"
    else:
        overall_rag = "on_track"

    return {
        "policy_version": POLICY_VERSION,
        "score": score,
        "rag": overall_rag,
        "label": _LABELS[overall_rag],
        "reasons": reasons or ["All monitored dimensions within configured thresholds"],
        "dimensions": dimensions,
        "open_risks": len(open_risks),
        "critical_risks": crit_risks,
        "blocked_tasks": blocked_tasks,
        "overdue_tasks": overdue_tasks,
    }
