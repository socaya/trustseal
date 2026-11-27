"""Enterprise REST APIs for TrustSeal Projects v2.0.

Blueprint families:
- ``portfolios_api``       -> ``/api/portfolios`` (PM-02)
- ``programmes_api``       -> ``/api/programmes`` (PM-03)
- ``project_intakes_api``  -> ``/api/project-intakes`` (PM-01)
- ``projects_v2_api``      -> ``/api/projects/<id>/{charter,gates,transition,wbs,dependencies,allocations,timesheets,budget,costs,changes,members,health}``
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from flask import Blueprint, abort, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.contract_workflow import ContractWorkflow, Project
from app.models.project_management import (
    ALLOCATION_STATUSES,
    CHANGE_STATUSES,
    CHANGE_TYPES,
    COST_EVENT_TYPES,
    DEPENDENCY_TYPES,
    GATE_STAGES,
    GATE_STATES,
    INTAKE_STATUSES,
    LIFECYCLE_STATES,
    PROJECT_ROLES,
    ProjectBudgetLine,
    ProjectChangeRequest,
    ProjectCharter,
    ProjectCostEvent,
    ProjectGate,
    ProjectIntake,
    ProjectMembership,
    ProjectPortfolio,
    ProjectProgramme,
    ProjectResourceAllocation,
    ProjectRisk,
    ProjectTask,
    ProjectTaskDependency,
    ProjectTimeEntry,
    ProjectWBSNode,
    parse_iso_date,
    to_decimal,
)
from app.models.user import User
from app.blueprints.projects.health_policy import evaluate_project_health
from app.blueprints.projects.permissions import (
    assert_project_mutable,
    can_approve_project_governance,
    can_view_project_finance,
    load_authorized_project,
)
from app.blueprints.projects.services import (
    approve_time_entry,
    compute_project_financials,
    convert_intake_to_project,
    count_overallocated_resources,
    dependency_would_cycle,
    emit_project_event,
    wbs_would_cycle,
)

portfolios_api = Blueprint("portfolios_api", __name__, url_prefix="/api/portfolios")
programmes_api = Blueprint("programmes_api", __name__, url_prefix="/api/programmes")
project_intakes_api = Blueprint("project_intakes_api", __name__, url_prefix="/api/project-intakes")
projects_v2_api = Blueprint("projects_v2_api", __name__, url_prefix="/api/projects")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _actor():
    if not current_user.is_authenticated:
        abort(401)
    if current_user.organization_id is None:
        abort(403, description="organization_required")
    return current_user


# =====================================================================
# PM-02: PORTFOLIOS (/api/portfolios)
# =====================================================================

@portfolios_api.route("", methods=["GET", "POST"])
@portfolios_api.route("/", methods=["GET", "POST"])
@login_required
def portfolios_collection():
    actor = _actor()
    org_id = actor.organization_id

    if request.method == "GET":
        rows = ProjectPortfolio.query.filter_by(organization_id=org_id).order_by(ProjectPortfolio.id.desc()).all()
        projs = Project.query.filter_by(organization_id=org_id).all()
        out = []
        for pf in rows:
            pf_projs = [p for p in projs if p.portfolio_id == pf.id]
            # Deduplicated sum in Decimal per currency
            budget_by_ccy: dict[str, Decimal] = {}
            for p in pf_projs:
                ccy = p.currency or "USD"
                budget_by_ccy[ccy] = budget_by_ccy.get(ccy, Decimal("0.00")) + p.effective_budget_decimal()
            out.append({
                **pf.to_dict(),
                "projects_count": len(pf_projs),
                "allocated_budget_by_currency": {k: str(v.quantize(Decimal("0.01"))) for k, v in budget_by_ccy.items()},
            })
        return jsonify({"ok": True, "portfolios": out})

    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()[:200]
    if not name:
        return jsonify({"error": "Portfolio name is required"}), 422
    cnt = ProjectPortfolio.query.filter_by(organization_id=org_id).count()
    code = str(data.get("code") or f"PF-{cnt + 1:03d}").strip()[:40]
    ceiling = to_decimal(data.get("budget_ceiling")) if data.get("budget_ceiling") not in (None, "") else None
    pf = ProjectPortfolio(
        organization_id=org_id,
        code=code,
        name=name,
        description=str(data.get("description") or "").strip() or None,
        strategic_objective=str(data.get("strategic_objective") or "").strip()[:300] or None,
        owner_user_id=actor.id,
        budget_ceiling=ceiling,
        currency=str(data.get("currency") or "USD").strip()[:12],
        status="active",
    )
    db.session.add(pf)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Portfolio code already exists in organization"}), 409
    emit_project_event(
        organization_id=org_id,
        actor_id=actor.id,
        event_type="portfolio.created",
        aggregate_type="project_portfolio",
        aggregate_id=pf.id,
        payload={"code": pf.code},
    )
    db.session.commit()
    return jsonify({"ok": True, "portfolio": pf.to_dict()}), 201


# =====================================================================
# PM-03: PROGRAMMES (/api/programmes)
# =====================================================================

@programmes_api.route("", methods=["GET", "POST"])
@programmes_api.route("/", methods=["GET", "POST"])
@login_required
def programmes_collection():
    actor = _actor()
    org_id = actor.organization_id

    if request.method == "GET":
        rows = ProjectProgramme.query.filter_by(organization_id=org_id).order_by(ProjectProgramme.id.desc()).all()
        projs = Project.query.filter_by(organization_id=org_id).all()
        out = []
        for pg in rows:
            pg_projs = [p for p in projs if p.programme_id == pg.id]
            out.append({**pg.to_dict(), "projects_count": len(pg_projs)})
        return jsonify({"ok": True, "programmes": out})

    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()[:200]
    if not name:
        return jsonify({"error": "Programme name is required"}), 422
    pf_id = data.get("portfolio_id")
    if pf_id:
        pf = ProjectPortfolio.query.filter_by(id=int(pf_id), organization_id=org_id).first()
        if pf is None:
            return jsonify({"error": "Portfolio not found in organization"}), 404
        pf_id = pf.id
    else:
        pf_id = None
    cnt = ProjectProgramme.query.filter_by(organization_id=org_id).count()
    code = str(data.get("code") or f"PRG-{cnt + 1:03d}").strip()[:40]
    ceiling = to_decimal(data.get("budget_ceiling")) if data.get("budget_ceiling") not in (None, "") else None
    pg = ProjectProgramme(
        organization_id=org_id,
        portfolio_id=pf_id,
        code=code,
        name=name,
        description=str(data.get("description") or "").strip() or None,
        sponsor_user_id=actor.id,
        manager_user_id=actor.id,
        budget_ceiling=ceiling,
        currency=str(data.get("currency") or "USD").strip()[:12],
        target_end_date=parse_iso_date(data.get("target_end_date")),
        status="active",
    )
    db.session.add(pg)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Programme code already exists in organization"}), 409
    emit_project_event(
        organization_id=org_id,
        actor_id=actor.id,
        event_type="programme.created",
        aggregate_type="project_programme",
        aggregate_id=pg.id,
        payload={"code": pg.code, "portfolio_id": pg.portfolio_id},
    )
    db.session.commit()
    return jsonify({"ok": True, "programme": pg.to_dict()}), 201


# =====================================================================
# PM-01: DEMAND & INVESTMENT INTAKE (/api/project-intakes)
# =====================================================================

@project_intakes_api.route("", methods=["GET", "POST"])
@project_intakes_api.route("/", methods=["GET", "POST"])
@login_required
def intakes_collection():
    actor = _actor()
    org_id = actor.organization_id

    if request.method == "GET":
        rows = ProjectIntake.query.filter_by(organization_id=org_id).order_by(ProjectIntake.weighted_score.desc(), ProjectIntake.id.desc()).all()
        return jsonify({"ok": True, "intakes": [r.to_dict() for r in rows]})

    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()[:220]
    if not title:
        return jsonify({"error": "Intake title is required"}), 422

    cnt = ProjectIntake.query.filter_by(organization_id=org_id).count()
    code = str(data.get("intake_code") or f"INT-{datetime.utcnow().year}-{cnt + 1:03d}").strip()[:40]

    def _clamp5(v, d=3):
        try:
            return max(1, min(5, int(v)))
        except (TypeError, ValueError):
            return d

    intake = ProjectIntake(
        organization_id=org_id,
        intake_code=code,
        title=title,
        problem_statement=str(data.get("problem_statement") or "").strip() or None,
        strategic_alignment=str(data.get("strategic_alignment") or "").strip()[:240] or None,
        category=str(data.get("category") or "client_delivery").strip()[:48],
        delivery_methodology=str(data.get("delivery_methodology") or "hybrid").strip()[:24],
        portfolio_id=int(data["portfolio_id"]) if str(data.get("portfolio_id") or "").isdigit() else None,
        programme_id=int(data["programme_id"]) if str(data.get("programme_id") or "").isdigit() else None,
        sponsor_user_id=actor.id,
        requester_user_id=actor.id,
        estimated_budget=to_decimal(data.get("estimated_budget")) if data.get("estimated_budget") not in (None, "") else None,
        currency=str(data.get("currency") or "USD").strip()[:12],
        value_score=_clamp5(data.get("value_score")),
        urgency_score=_clamp5(data.get("urgency_score")),
        feasibility_score=_clamp5(data.get("feasibility_score")),
        risk_score=_clamp5(data.get("risk_score")),
        status="submitted",
    )
    intake.weighted_score = intake.compute_weighted_score()
    db.session.add(intake)
    db.session.flush()
    emit_project_event(
        organization_id=org_id,
        actor_id=actor.id,
        event_type="intake.submitted",
        aggregate_type="project_intake",
        aggregate_id=intake.id,
        payload={"intake_code": intake.intake_code, "weighted_score": str(intake.weighted_score)},
    )
    db.session.commit()
    return jsonify({"ok": True, "intake": intake.to_dict()}), 201


@project_intakes_api.route("/<int:intake_id>/decide", methods=["POST"])
@login_required
def decide_intake(intake_id: int):
    actor = _actor()
    intake = ProjectIntake.query.filter_by(id=intake_id, organization_id=actor.organization_id).first()
    if intake is None:
        abort(404)
    data = request.get_json(silent=True) or {}
    decision = str(data.get("decision") or "").strip().lower()
    if decision not in INTAKE_STATUSES:
        return jsonify({"error": f"Invalid decision; must be one of {INTAKE_STATUSES}"}), 422
    rationale = str(data.get("rationale") or "").strip()
    if decision == "rejected" and not rationale:
        return jsonify({"error": "Rejection rationale is required"}), 422
    if intake.status == "rejected" and decision == "approved":
        return jsonify({"error": "Rejected intake cannot silently become active; submit a new request"}), 409

    intake.status = decision
    intake.decision_rationale = rationale or intake.decision_rationale
    intake.decided_by_id = actor.id
    intake.decided_at = _utcnow()
    emit_project_event(
        organization_id=actor.organization_id,
        actor_id=actor.id,
        event_type=f"intake.{decision}",
        aggregate_type="project_intake",
        aggregate_id=intake.id,
        payload={"decision": decision},
    )
    db.session.commit()
    return jsonify({"ok": True, "intake": intake.to_dict()})


@project_intakes_api.route("/<int:intake_id>/convert", methods=["POST"])
@login_required
def convert_intake(intake_id: int):
    actor = _actor()
    intake = ProjectIntake.query.filter_by(id=intake_id, organization_id=actor.organization_id).first()
    if intake is None:
        abort(404)
    try:
        proj, created_now = convert_intake_to_project(intake, actor)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409
    db.session.commit()
    return jsonify({
        "ok": True,
        "created": created_now,
        "intake": intake.to_dict(),
        "project": proj.to_dict(),
    }), (201 if created_now else 200)


# =====================================================================
# PM-04: CHARTER, STAGE GATES & LIFECYCLE TRANSITIONS
# =====================================================================

@projects_v2_api.route("/<int:project_id>/charter", methods=["GET", "POST"])
@login_required
def project_charter(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))

    if request.method == "GET":
        rows = ProjectCharter.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).order_by(ProjectCharter.version.desc()).all()
        return jsonify({"ok": True, "charters": [r.to_dict() for r in rows]})

    assert_project_mutable(proj)
    data = request.get_json(silent=True) or {}
    latest = ProjectCharter.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).order_by(ProjectCharter.version.desc()).first()
    next_ver = (latest.version + 1) if latest else 1
    if latest and latest.status == "draft":
        latest.status = "superseded"
    charter = ProjectCharter(
        organization_id=proj.organization_id,
        project_id=proj.id,
        version=next_ver,
        objectives=str(data.get("objectives") or "").strip() or None,
        scope_in=str(data.get("scope_in") or "").strip() or None,
        scope_out=str(data.get("scope_out") or "").strip() or None,
        success_criteria=str(data.get("success_criteria") or "").strip() or None,
        cost_tolerance_pct=to_decimal(data.get("cost_tolerance_pct"), "10.00"),
        schedule_tolerance_days=int(data.get("schedule_tolerance_days") or 14),
        status="draft",
        created_by_id=actor.id,
    )
    db.session.add(charter)
    db.session.flush()
    emit_project_event(
        organization_id=proj.organization_id,
        actor_id=actor.id,
        event_type="charter.drafted",
        aggregate_type="project_charter",
        aggregate_id=charter.id,
        payload={"project_id": proj.id, "version": next_ver},
    )
    db.session.commit()
    return jsonify({"ok": True, "charter": charter.to_dict()}), 201


@projects_v2_api.route("/<int:project_id>/charter/<int:charter_id>/approve", methods=["POST"])
@login_required
def approve_project_charter(project_id: int, charter_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    if not can_approve_project_governance(proj, actor):
        abort(403, description="governance_approval_required")
    charter = ProjectCharter.query.filter_by(id=charter_id, project_id=proj.id, organization_id=proj.organization_id).first()
    if charter is None:
        abort(404)
    # Supersede previously approved charters
    for old in ProjectCharter.query.filter_by(project_id=proj.id, status="approved").all():
        if old.id != charter.id:
            old.status = "superseded"
    charter.status = "approved"
    charter.approved_by_id = actor.id
    charter.approved_at = _utcnow()
    emit_project_event(
        organization_id=proj.organization_id,
        actor_id=actor.id,
        event_type="baseline.approved",
        aggregate_type="project_charter",
        aggregate_id=charter.id,
        payload={"project_id": proj.id, "charter_version": charter.version},
    )
    db.session.commit()
    return jsonify({"ok": True, "charter": charter.to_dict()})


@projects_v2_api.route("/<int:project_id>/gates", methods=["GET"])
@login_required
def list_project_gates(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor)
    rows = ProjectGate.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).all()
    by_stage = {g.stage: g.to_dict() for g in rows}
    ordered = [
        by_stage.get(st, {"project_id": proj.id, "stage": st, "gate_state": "not_ready", "decision_note": ""})
        for st in GATE_STAGES
    ]
    return jsonify({"ok": True, "lifecycle_state": proj.lifecycle_state, "gates": ordered})


@projects_v2_api.route("/<int:project_id>/gates/<stage>/decide", methods=["POST"])
@login_required
def decide_project_gate(project_id: int, stage: str):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    if stage not in GATE_STAGES:
        return jsonify({"error": f"Unknown stage '{stage}'"}), 422
    data = request.get_json(silent=True) or {}
    new_state = str(data.get("gate_state") or "approved").strip().lower()
    if new_state not in GATE_STATES:
        return jsonify({"error": f"Invalid gate_state '{new_state}'"}), 422
    if new_state in ("approved", "rejected") and not can_approve_project_governance(proj, actor):
        abort(403, description="governance_approval_required")

    gate = ProjectGate.query.filter_by(organization_id=proj.organization_id, project_id=proj.id, stage=stage).first()
    if gate is None:
        gate = ProjectGate(organization_id=proj.organization_id, project_id=proj.id, stage=stage)
        db.session.add(gate)
    gate.gate_state = new_state
    gate.decision_note = str(data.get("decision_note") or "").strip() or None
    gate.waiver_reason = str(data.get("waiver_reason") or "").strip() or None
    if new_state == "submitted":
        gate.submitted_by_id = actor.id
    elif new_state in ("approved", "rejected", "returned"):
        gate.decided_by_id = actor.id
        gate.decided_at = _utcnow()
    gate.evidence_snapshot_json = {
        "lifecycle_state": proj.lifecycle_state,
        "decided_at": _utcnow().isoformat(),
        "actor_id": actor.id,
    }
    db.session.flush()
    emit_project_event(
        organization_id=proj.organization_id,
        actor_id=actor.id,
        event_type="project.gate_decided",
        aggregate_type="project_gate",
        aggregate_id=gate.id,
        payload={"project_id": proj.id, "stage": stage, "gate_state": new_state},
    )
    db.session.commit()
    return jsonify({"ok": True, "gate": gate.to_dict()})


@projects_v2_api.route("/<int:project_id>/transition", methods=["POST"])
@login_required
def transition_project(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    if not can_approve_project_governance(proj, actor):
        abort(403, description="governance_approval_required")
    data = request.get_json(silent=True) or {}
    target = str(data.get("lifecycle_state") or "").strip().lower()
    if target not in LIFECYCLE_STATES:
        return jsonify({"error": f"Invalid lifecycle_state '{target}'"}), 422

    # Closed projects can only transition via explicit audited reopen or archive
    if proj.lifecycle_state == "closed" and target not in ("archived", "executing"):
        return jsonify({"error": "Closed project is read-only; only archive or audited reopen is permitted"}), 409

    # Closure gate check: block closure if critical open risks or unapproved time entries exist unless waiver provided
    if target == "closed":
        crit_open = ProjectRisk.query.filter_by(
            organization_id=proj.organization_id, project_id=proj.id, severity="critical"
        ).filter(ProjectRisk.status.notin_(("closed", "mitigated"))).count()
        unapproved_time = ProjectTimeEntry.query.filter_by(
            organization_id=proj.organization_id, project_id=proj.id
        ).filter(ProjectTimeEntry.status.in_(("draft", "submitted", "returned"))).count()
        waiver = str(data.get("waiver_reason") or "").strip()
        if (crit_open > 0 or unapproved_time > 0) and not waiver:
            return jsonify({
                "error": f"Closure blocked by {crit_open} critical open risk(s) and {unapproved_time} unapproved time entry(ies). Resolve or provide authorized waiver_reason."
            }), 409
        # Release future confirmed resource bookings on closure (Spec Section 5 PM-12)
        for alloc in ProjectResourceAllocation.query.filter_by(
            organization_id=proj.organization_id, project_id=proj.id, status="confirmed"
        ).all():
            alloc.status = "released"

    old_state = proj.lifecycle_state
    proj.lifecycle_state = target
    if target in ("closed", "archived"):
        proj.status = "completed" if target == "closed" else "archived"
    elif target == "on_hold":
        proj.status = "on_hold"
    elif target == "executing":
        proj.status = "active"
    proj.version = int(proj.version or 1) + 1

    emit_project_event(
        organization_id=proj.organization_id,
        actor_id=actor.id,
        event_type="project.closed" if target == "closed" else "project.stage_changed",
        aggregate_type="project",
        aggregate_id=proj.id,
        payload={"from_state": old_state, "to_state": target, "note": str(data.get("note") or "")[:200]},
    )
    db.session.commit()
    return jsonify({"ok": True, "project": proj.to_dict()})


# =====================================================================
# PM-06: WBS WORK PACKAGES (/api/projects/<id>/wbs)
# =====================================================================

@projects_v2_api.route("/<int:project_id>/wbs", methods=["GET", "POST"])
@login_required
def project_wbs_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))

    if request.method == "GET":
        rows = ProjectWBSNode.query.filter_by(
            organization_id=proj.organization_id, project_id=proj.id
        ).order_by(ProjectWBSNode.sort_order.asc(), ProjectWBSNode.id.asc()).all()
        return jsonify({"ok": True, "wbs": [r.to_dict() for r in rows]})

    assert_project_mutable(proj)
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()[:220]
    if not title:
        return jsonify({"error": "WBS title is required"}), 422
    parent_id = int(data["parent_id"]) if str(data.get("parent_id") or "").isdigit() else None
    if parent_id is not None:
        parent = ProjectWBSNode.query.filter_by(id=parent_id, project_id=proj.id, organization_id=proj.organization_id).first()
        if parent is None:
            return jsonify({"error": "Parent WBS node not found in project"}), 404

    cnt = ProjectWBSNode.query.filter_by(project_id=proj.id).count()
    code = str(data.get("wbs_code") or f"WBS-{cnt + 1}").strip()[:32]
    node = ProjectWBSNode(
        organization_id=proj.organization_id,
        project_id=proj.id,
        parent_id=parent_id,
        wbs_code=code,
        title=title,
        node_type=str(data.get("node_type") or "work_package").strip()[:24],
        owner_user_id=int(data["owner_user_id"]) if str(data.get("owner_user_id") or "").isdigit() else actor.id,
        budget_allocation=to_decimal(data.get("budget_allocation")),
        weight_pct=max(0, min(100, int(data.get("weight_pct") or 0))),
        sort_order=int(data.get("sort_order") or cnt),
    )
    db.session.add(node)
    db.session.commit()
    return jsonify({"ok": True, "node": node.to_dict()}), 201


@projects_v2_api.route("/<int:project_id>/wbs/<int:node_id>", methods=["PATCH", "DELETE"])
@login_required
def project_wbs_item(project_id: int, node_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    assert_project_mutable(proj)
    node = ProjectWBSNode.query.filter_by(id=node_id, project_id=proj.id, organization_id=proj.organization_id).first()
    if node is None:
        abort(404)

    if request.method == "DELETE":
        db.session.delete(node)
        db.session.commit()
        return jsonify({"ok": True, "deleted": node_id})

    data = request.get_json(silent=True) or {}
    if "parent_id" in data:
        new_pid = int(data["parent_id"]) if str(data.get("parent_id") or "").isdigit() else None
        if wbs_would_cycle(proj.id, node.id, new_pid):
            return jsonify({"error": "Reparenting would create a WBS hierarchy cycle"}), 422
        node.parent_id = new_pid
    if "title" in data and str(data["title"]).strip():
        node.title = str(data["title"]).strip()[:220]
    if "budget_allocation" in data:
        node.budget_allocation = to_decimal(data["budget_allocation"])
    if "weight_pct" in data:
        node.weight_pct = max(0, min(100, int(data["weight_pct"] or 0)))
    db.session.commit()
    return jsonify({"ok": True, "node": node.to_dict()})


# =====================================================================
# PM-07: TASK DEPENDENCIES (/api/projects/<id>/dependencies)
# =====================================================================

@projects_v2_api.route("/<int:project_id>/dependencies", methods=["GET", "POST"])
@login_required
def project_dependencies_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))

    if request.method == "GET":
        rows = ProjectTaskDependency.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).all()
        return jsonify({"ok": True, "dependencies": [r.to_dict() for r in rows]})

    assert_project_mutable(proj)
    data = request.get_json(silent=True) or {}
    pred_id = data.get("predecessor_task_id")
    succ_id = data.get("successor_task_id")
    if not str(pred_id or "").isdigit() or not str(succ_id or "").isdigit():
        return jsonify({"error": "predecessor_task_id and successor_task_id are required"}), 422
    pred_id, succ_id = int(pred_id), int(succ_id)

    pred = ProjectTask.query.filter_by(id=pred_id, project_id=proj.id, organization_id=proj.organization_id).first()
    succ = ProjectTask.query.filter_by(id=succ_id, project_id=proj.id, organization_id=proj.organization_id).first()
    if pred is None or succ is None:
        return jsonify({"error": "Both tasks must belong to this project"}), 404

    if dependency_would_cycle(proj.id, pred_id, succ_id):
        return jsonify({"error": "Dependency rejected: creates a schedule cycle"}), 422

    dep_type = str(data.get("dependency_type") or "FS").strip().upper()
    if dep_type not in DEPENDENCY_TYPES:
        dep_type = "FS"

    dep = ProjectTaskDependency(
        organization_id=proj.organization_id,
        project_id=proj.id,
        predecessor_task_id=pred_id,
        successor_task_id=succ_id,
        dependency_type=dep_type,
        lag_days=int(data.get("lag_days") or 0),
    )
    db.session.add(dep)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Dependency already exists"}), 409
    return jsonify({"ok": True, "dependency": dep.to_dict()}), 201


@projects_v2_api.route("/<int:project_id>/dependencies/<int:dep_id>", methods=["DELETE"])
@login_required
def delete_project_dependency(project_id: int, dep_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    dep = ProjectTaskDependency.query.filter_by(id=dep_id, project_id=proj.id, organization_id=proj.organization_id).first()
    if dep is None:
        abort(404)
    db.session.delete(dep)
    db.session.commit()
    return jsonify({"ok": True, "deleted": dep_id})


# =====================================================================
# PM-12: RESOURCE ALLOCATIONS (/api/projects/<id>/allocations)
# =====================================================================

@projects_v2_api.route("/<int:project_id>/allocations", methods=["GET", "POST"])
@login_required
def project_allocations_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))
    show_rates = can_view_project_finance(proj, actor)

    if request.method == "GET":
        rows = ProjectResourceAllocation.query.filter_by(
            organization_id=proj.organization_id, project_id=proj.id
        ).order_by(ProjectResourceAllocation.id.desc()).all()
        return jsonify({"ok": True, "allocations": [r.to_dict(include_rates=show_rates) for r in rows]})

    assert_project_mutable(proj)
    data = request.get_json(silent=True) or {}
    user_id = int(data["user_id"]) if str(data.get("user_id") or "").isdigit() else None
    res_name = str(data.get("resource_name") or "").strip()[:160]
    if user_id and not res_name:
        u = User.query.filter_by(id=user_id, organization_id=proj.organization_id).first()
        if u is None:
            return jsonify({"error": "User not found in organization"}), 404
        res_name = getattr(u, "full_name", None) or u.username or u.email
    if not res_name:
        return jsonify({"error": "resource_name or user_id is required"}), 422

    pct = max(1, min(200, int(data.get("allocation_pct") or 50)))
    status = str(data.get("status") or "confirmed").strip().lower()
    if status not in ALLOCATION_STATUSES:
        status = "confirmed"

    # Hard-limit capacity check across active projects for this user unless override_capacity=True
    if user_id and status == "confirmed":
        existing_pct = sum(
            int(a.allocation_pct or 0)
            for a in ProjectResourceAllocation.query.filter_by(
                organization_id=proj.organization_id, user_id=user_id, status="confirmed"
            ).all()
        )
        if existing_pct + pct > 100 and not data.get("override_capacity"):
            return jsonify({
                "error": f"Capacity conflict: user already allocated at {existing_pct}%; adding {pct}% exceeds 100% capacity.",
                "existing_allocation_pct": existing_pct,
                "requested_pct": pct,
            }), 409

    alloc = ProjectResourceAllocation(
        organization_id=proj.organization_id,
        project_id=proj.id,
        user_id=user_id,
        resource_name=res_name,
        role_title=str(data.get("role_title") or "Contributor").strip()[:120],
        allocation_pct=pct,
        planned_hours=to_decimal(data.get("planned_hours")),
        hourly_cost_rate=to_decimal(data.get("hourly_cost_rate")) if data.get("hourly_cost_rate") not in (None, "") else None,
        currency=str(data.get("currency") or proj.currency or "USD").strip()[:12],
        start_date=parse_iso_date(data.get("start_date")),
        end_date=parse_iso_date(data.get("end_date")),
        status=status,
        created_by_id=actor.id,
    )
    db.session.add(alloc)
    db.session.flush()
    emit_project_event(
        organization_id=proj.organization_id,
        actor_id=actor.id,
        event_type="resource.allocation_approved",
        aggregate_type="project_resource_allocation",
        aggregate_id=alloc.id,
        payload={"project_id": proj.id, "allocation_pct": pct},
    )
    db.session.commit()
    return jsonify({"ok": True, "allocation": alloc.to_dict(include_rates=show_rates)}), 201


@projects_v2_api.route("/<int:project_id>/allocations/<int:alloc_id>", methods=["DELETE"])
@login_required
def delete_project_allocation(project_id: int, alloc_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    alloc = ProjectResourceAllocation.query.filter_by(id=alloc_id, project_id=proj.id, organization_id=proj.organization_id).first()
    if alloc is None:
        abort(404)
    db.session.delete(alloc)
    db.session.commit()
    return jsonify({"ok": True, "deleted": alloc_id})


# =====================================================================
# PM-13: TIMESHEETS & EFFORT ACCOUNTING (/api/projects/<id>/timesheets)
# =====================================================================

@projects_v2_api.route("/<int:project_id>/timesheets", methods=["GET", "POST"])
@login_required
def project_timesheets_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))
    show_rates = can_view_project_finance(proj, actor)

    if request.method == "GET":
        rows = ProjectTimeEntry.query.filter_by(
            organization_id=proj.organization_id, project_id=proj.id
        ).order_by(ProjectTimeEntry.work_date.desc(), ProjectTimeEntry.id.desc()).all()
        return jsonify({"ok": True, "time_entries": [r.to_dict(include_rates=show_rates) for r in rows]})

    assert_project_mutable(proj)
    data = request.get_json(silent=True) or {}
    hours = to_decimal(data.get("hours"))
    if hours <= Decimal("0.00") or hours > Decimal("24.00"):
        return jsonify({"error": "hours must be between 0.01 and 24.00"}), 422
    wdate = parse_iso_date(data.get("work_date")) or datetime.utcnow().date()
    tid = int(data["task_id"]) if str(data.get("task_id") or "").isdigit() else None
    if tid is not None:
        if ProjectTask.query.filter_by(id=tid, project_id=proj.id, organization_id=proj.organization_id).first() is None:
            return jsonify({"error": "Task not found in project"}), 404

    entry = ProjectTimeEntry(
        organization_id=proj.organization_id,
        project_id=proj.id,
        task_id=tid,
        user_id=actor.id,
        work_date=wdate,
        hours=hours,
        billable=bool(data.get("billable", True)),
        notes=str(data.get("notes") or "").strip()[:400] or None,
        currency=str(data.get("currency") or proj.currency or "USD").strip()[:12],
        status="submitted" if data.get("submit") else "draft",
    )
    db.session.add(entry)
    db.session.commit()
    return jsonify({"ok": True, "time_entry": entry.to_dict(include_rates=show_rates)}), 201


@projects_v2_api.route("/<int:project_id>/timesheets/<int:entry_id>/approve", methods=["POST"])
@login_required
def approve_project_timesheet(project_id: int, entry_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    if not can_approve_project_governance(proj, actor):
        abort(403, description="timesheet_approval_required")
    entry = ProjectTimeEntry.query.filter_by(id=entry_id, project_id=proj.id, organization_id=proj.organization_id).first()
    if entry is None:
        abort(404)
    data = request.get_json(silent=True) or {}
    explicit_rate = to_decimal(data.get("hourly_rate")) if data.get("hourly_rate") not in (None, "") else None
    ev = approve_time_entry(entry, proj, actor, hourly_rate=explicit_rate)
    db.session.commit()
    return jsonify({
        "ok": True,
        "time_entry": entry.to_dict(include_rates=can_view_project_finance(proj, actor)),
        "cost_event": ev.to_dict(),
    })


# =====================================================================
# PM-15 & PM-16: DECIMAL BUDGETING & COST LEDGER
# =====================================================================

@projects_v2_api.route("/<int:project_id>/budget", methods=["GET", "POST"])
@login_required
def project_budget_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))
    if not can_view_project_finance(proj, actor):
        abort(403, description="finance_permission_required")

    if request.method == "GET":
        lines = ProjectBudgetLine.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).order_by(ProjectBudgetLine.id.asc()).all()
        fin = compute_project_financials(proj, budget_lines=lines)
        return jsonify({
            "ok": True,
            "budget_lines": [l.to_dict() for l in lines],
            "summary": {k: v for k, v in fin.items() if isinstance(v, (str, int))},
        })

    assert_project_mutable(proj)
    data = request.get_json(silent=True) or {}
    desc = str(data.get("description") or "").strip()[:240]
    if not desc:
        return jsonify({"error": "Budget line description is required"}), 422
    amt = to_decimal(data.get("planned_amount"))
    if amt < Decimal("0.00"):
        return jsonify({"error": "planned_amount must be non-negative"}), 422

    line = ProjectBudgetLine(
        organization_id=proj.organization_id,
        project_id=proj.id,
        wbs_node_id=int(data["wbs_node_id"]) if str(data.get("wbs_node_id") or "").isdigit() else None,
        category=str(data.get("category") or "labor").strip()[:48],
        description=desc,
        planned_amount=amt,
        currency=str(data.get("currency") or proj.currency or "USD").strip()[:12],
        baseline_version=int(data.get("baseline_version") or 1),
        created_by_id=actor.id,
    )
    db.session.add(line)
    db.session.commit()
    return jsonify({"ok": True, "budget_line": line.to_dict()}), 201


@projects_v2_api.route("/<int:project_id>/costs", methods=["GET", "POST"])
@login_required
def project_costs_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))
    if not can_view_project_finance(proj, actor):
        abort(403, description="finance_permission_required")

    if request.method == "GET":
        events = ProjectCostEvent.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).order_by(ProjectCostEvent.id.desc()).all()
        fin = compute_project_financials(proj, cost_events=events)
        return jsonify({
            "ok": True,
            "cost_events": [e.to_dict() for e in events],
            "summary": {k: v for k, v in fin.items() if isinstance(v, (str, int))},
        })

    assert_project_mutable(proj)
    data = request.get_json(silent=True) or {}
    desc = str(data.get("description") or "").strip()[:240]
    if not desc:
        return jsonify({"error": "Cost event description is required"}), 422
    etype = str(data.get("event_type") or "actual").strip().lower()
    if etype not in COST_EVENT_TYPES:
        return jsonify({"error": f"Invalid event_type; must be one of {COST_EVENT_TYPES}"}), 422
    amt = to_decimal(data.get("amount"))
    sref = str(data.get("source_ref") or "").strip()[:120] or None

    ev = ProjectCostEvent(
        organization_id=proj.organization_id,
        project_id=proj.id,
        wbs_node_id=int(data["wbs_node_id"]) if str(data.get("wbs_node_id") or "").isdigit() else None,
        event_type=etype,
        category=str(data.get("category") or "vendor").strip()[:48],
        description=desc,
        amount=amt,
        currency=str(data.get("currency") or proj.currency or "USD").strip()[:12],
        source_ref=sref,
        status="posted",
        event_date=parse_iso_date(data.get("event_date")) or datetime.utcnow().date(),
        created_by_id=actor.id,
    )
    db.session.add(ev)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Duplicate source_ref: cost event already posted"}), 409

    emit_project_event(
        organization_id=proj.organization_id,
        actor_id=actor.id,
        event_type="cost.posted",
        aggregate_type="project_cost_event",
        aggregate_id=ev.id,
        payload={"project_id": proj.id, "event_type": etype, "currency": ev.currency},
    )
    db.session.commit()
    return jsonify({"ok": True, "cost_event": ev.to_dict()}), 201


# =====================================================================
# PM-20: INTEGRATED CHANGE CONTROL (/api/projects/<id>/changes)
# =====================================================================

@projects_v2_api.route("/<int:project_id>/changes", methods=["GET", "POST"])
@login_required
def project_changes_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))

    if request.method == "GET":
        rows = ProjectChangeRequest.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).order_by(ProjectChangeRequest.id.desc()).all()
        return jsonify({"ok": True, "changes": [r.to_dict() for r in rows]})

    assert_project_mutable(proj)
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()[:220]
    if not title:
        return jsonify({"error": "Change request title is required"}), 422
    ctype = str(data.get("change_type") or "scope").strip().lower()
    if ctype not in CHANGE_TYPES:
        ctype = "scope"
    cnt = ProjectChangeRequest.query.filter_by(project_id=proj.id).count()
    cr = ProjectChangeRequest(
        organization_id=proj.organization_id,
        project_id=proj.id,
        cr_number=f"CR-{cnt + 1:03d}",
        title=title,
        change_type=ctype,
        rationale=str(data.get("rationale") or "").strip() or None,
        cost_impact=to_decimal(data.get("cost_impact")),
        schedule_impact_days=int(data.get("schedule_impact_days") or 0),
        status="submitted",
        requested_by_id=actor.id,
    )
    db.session.add(cr)
    db.session.commit()
    return jsonify({"ok": True, "change": cr.to_dict()}), 201


@projects_v2_api.route("/<int:project_id>/changes/<int:cr_id>/decide", methods=["POST"])
@login_required
def decide_project_change(project_id: int, cr_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    if not can_approve_project_governance(proj, actor):
        abort(403, description="governance_approval_required")
    cr = ProjectChangeRequest.query.filter_by(id=cr_id, project_id=proj.id, organization_id=proj.organization_id).first()
    if cr is None:
        abort(404)
    data = request.get_json(silent=True) or {}
    decision = str(data.get("decision") or "").strip().lower()
    if decision not in ("approved", "rejected", "implemented"):
        return jsonify({"error": "decision must be approved, rejected, or implemented"}), 422

    cr.status = decision
    cr.decision_note = str(data.get("decision_note") or "").strip() or None
    cr.decided_by_id = actor.id
    cr.decided_at = _utcnow()
    if decision == "approved":
        emit_project_event(
            organization_id=proj.organization_id,
            actor_id=actor.id,
            event_type="change.approved",
            aggregate_type="project_change_request",
            aggregate_id=cr.id,
            payload={"project_id": proj.id, "cr_number": cr.cr_number},
        )
    db.session.commit()
    return jsonify({"ok": True, "change": cr.to_dict()})


# =====================================================================
# PM-33: PROJECT MEMBERSHIPS (/api/projects/<id>/members)
# =====================================================================

@projects_v2_api.route("/<int:project_id>/members", methods=["GET", "POST"])
@login_required
def project_members_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))

    if request.method == "GET":
        rows = ProjectMembership.query.filter_by(organization_id=proj.organization_id, project_id=proj.id, is_active=True).all()
        uids = [r.user_id for r in rows]
        users = {u.id: u for u in User.query.filter(User.id.in_(uids)).all()} if uids else {}
        out = []
        for r in rows:
            u = users.get(r.user_id)
            out.append({
                **r.to_dict(),
                "username": u.username if u else "",
                "email": u.email if u else "",
            })
        return jsonify({"ok": True, "members": out})

    if not can_approve_project_governance(proj, actor):
        abort(403, description="member_management_required")
    data = request.get_json(silent=True) or {}
    uid = data.get("user_id")
    if not str(uid or "").isdigit():
        return jsonify({"error": "user_id is required"}), 422
    u = User.query.filter_by(id=int(uid), organization_id=proj.organization_id).first()
    if u is None:
        return jsonify({"error": "User not found in organization"}), 404
    role = str(data.get("project_role") or "member").strip().lower()
    if role not in PROJECT_ROLES:
        return jsonify({"error": f"Invalid project_role; must be one of {PROJECT_ROLES}"}), 422

    mem = ProjectMembership.query.filter_by(project_id=proj.id, user_id=u.id).first()
    if mem is None:
        mem = ProjectMembership(
            organization_id=proj.organization_id,
            project_id=proj.id,
            user_id=u.id,
            granted_by_id=actor.id,
        )
        db.session.add(mem)
    mem.project_role = role
    mem.can_view_finance = bool(data.get("can_view_finance", role in ("sponsor", "pmo", "project_manager", "finance")))
    mem.is_active = True
    db.session.commit()
    return jsonify({"ok": True, "member": {**mem.to_dict(), "username": u.username, "email": u.email}}), 201


@projects_v2_api.route("/<int:project_id>/members/<int:member_id>", methods=["DELETE"])
@login_required
def remove_project_member(project_id: int, member_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    if not can_approve_project_governance(proj, actor):
        abort(403, description="member_management_required")
    mem = ProjectMembership.query.filter_by(id=member_id, project_id=proj.id, organization_id=proj.organization_id).first()
    if mem is None:
        abort(404)
    mem.is_active = False
    db.session.commit()
    return jsonify({"ok": True, "revoked": member_id})


# =====================================================================
# PM-27: EXPLAINABLE HEALTH POLICY ENDPOINT (/api/projects/<id>/health)
# =====================================================================

@projects_v2_api.route("/<int:project_id>/health", methods=["GET"])
@login_required
def project_health_detail(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor)
    tasks = ProjectTask.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).all()
    risks = ProjectRisk.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).all()
    wfs = ContractWorkflow.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).all()
    susp_cnt = sum(1 for w in wfs if w.canonical_status() == "SUSPENDED")
    fin = compute_project_financials(proj)
    overalloc = count_overallocated_resources(proj.organization_id, proj.id)
    health = evaluate_project_health(
        budget_util_pct=fin["budget_util_pct"],
        suspended_contracts=susp_cnt,
        tasks=tasks,
        risks=risks,
        available_budget=fin["available_budget"],
        approved_budget=fin["approved_budget"],
        overallocated_resources=overalloc,
    )
    return jsonify({"ok": True, "health": health})
