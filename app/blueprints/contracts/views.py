"""HTML views for Projects Hub and Contract Templates Studio."""
from __future__ import annotations

from flask import Blueprint, abort, render_template, request
from flask_login import current_user, login_required

from app.models.contract_workflow import (
    CONTRACT_STATUSES,
    CONTRACT_TYPES,
    ContractDeliverable,
    ContractKeyTerm,
    ContractWorkflow,
    PROJECT_CATEGORIES,
    Project,
    ensure_contract_workflow_table,
)
from app.models.tsd_document import TSDocument
from app.blueprints.contracts.lifecycle_service import (
    compute_deliverable_progress,
    ensure_default_project,
    ensure_default_templates,
)


contracts_views = Blueprint("contracts_views", __name__)


def _actor():
    if not current_user.is_authenticated:
        abort(401)
    if current_user.organization_id is None:
        abort(403, description="organization_required")
    return current_user


def _parse_num_val(raw: str | None) -> float:
    if not raw:
        return 0.0
    cleaned = "".join(ch for ch in str(raw) if ch.isdigit() or ch == ".")
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


@contracts_views.route("/projects", methods=["GET"])
@login_required
def projects_page():
    actor = _actor()
    org_id = actor.organization_id
    ensure_contract_workflow_table()
    ensure_default_project(org_id, actor)

    from app.models.project_management import (
        ProjectRisk,
        ProjectTask,
        compute_project_health,
        ensure_project_management_tables,
    )

    ensure_project_management_tables()
    projects = (
        Project.query.filter_by(organization_id=org_id)
        .order_by(Project.is_default.desc(), Project.updated_at.desc())
        .all()
    )
    wf_rows = ContractWorkflow.query.filter_by(organization_id=org_id).all()
    deliv_rows = ContractDeliverable.query.filter_by(organization_id=org_id).all()
    kt_rows = ContractKeyTerm.query.filter_by(organization_id=org_id).all()
    task_rows_all = ProjectTask.query.filter_by(organization_id=org_id).all()
    risk_rows_all = ProjectRisk.query.filter_by(organization_id=org_id).all()

    deliv_by_wf: dict[int, list[ContractDeliverable]] = {}
    for d in deliv_rows:
        deliv_by_wf.setdefault(d.contract_id, []).append(d)
    kt_by_wf: dict[int, list[ContractKeyTerm]] = {}
    for k in kt_rows:
        kt_by_wf.setdefault(k.contract_id, []).append(k)
    tasks_by_proj: dict[int, list[ProjectTask]] = {}
    for t in task_rows_all:
        tasks_by_proj.setdefault(t.project_id, []).append(t)
    risks_by_proj: dict[int, list[ProjectRisk]] = {}
    for r in risk_rows_all:
        risks_by_proj.setdefault(r.project_id, []).append(r)

    project_cards = []
    all_delivs: list[ContractDeliverable] = []
    total_budget = 0.0
    total_committed = 0.0
    total_probations = 0
    total_open_tasks = 0
    total_open_risks = 0
    for p in projects:
        p_wfs = [w for w in wf_rows if w.project_id == p.id]
        p_delivs = [d for w in p_wfs for d in deliv_by_wf.get(w.id, [])]
        p_kts = [k for w in p_wfs for k in kt_by_wf.get(w.id, [])]
        p_tasks = tasks_by_proj.get(p.id, [])
        p_risks = risks_by_proj.get(p.id, [])
        all_delivs.extend(p_delivs)
        prog = compute_deliverable_progress(p_delivs)
        committed = sum(_parse_num_val(w.deal_value) for w in p_wfs)
        total_committed += committed
        prob_cnt = sum(1 for k in p_kts if k.category == "probation" and k.status == "active")
        total_probations += prob_cnt
        if p.budget_amount:
            total_budget += float(p.budget_amount)
        util_pct = (
            min(150, int(round((committed / float(p.budget_amount)) * 100)))
            if p.budget_amount and float(p.budget_amount) > 0
            else 0
        )
        susp_cnt = sum(1 for w in p_wfs if w.canonical_status() == "SUSPENDED")
        health = compute_project_health(
            budget_util_pct=util_pct,
            suspended_contracts=susp_cnt,
            tasks=p_tasks,
            risks=p_risks,
        )
        open_t = sum(1 for t in p_tasks if (t.status or "todo") != "done")
        done_t = sum(1 for t in p_tasks if (t.status or "") == "done")
        total_open_tasks += open_t
        total_open_risks += health["open_risks"]
        project_cards.append({
            **p.to_dict(),
            "contracts_total": len(p_wfs),
            "contracts_signed": sum(1 for w in p_wfs if w.canonical_status() == "SIGNED"),
            "contracts_draft": sum(1 for w in p_wfs if w.canonical_status() == "DRAFT"),
            "contracts_suspended": susp_cnt,
            "contracts_terminated": sum(1 for w in p_wfs if w.canonical_status() == "TERMINATED"),
            "deliverables_total": prog["total"],
            "deliverables_accepted": prog["accepted"],
            "deliverables_pct": prog["pct"],
            "key_terms_total": len(p_kts),
            "probations_active": prob_cnt,
            "committed_value": committed,
            "budget_util_pct": util_pct,
            "tasks_total": len(p_tasks),
            "tasks_done": done_t,
            "tasks_open": open_t,
            "open_risks": health["open_risks"],
            "health": health,
        })

    from app.models.project_management import (
        ProjectIntake,
        ProjectPortfolio,
        ProjectProgramme,
    )

    portfolios_list = [
        pf.to_dict()
        for pf in ProjectPortfolio.query.filter_by(organization_id=org_id)
        .order_by(ProjectPortfolio.id.desc())
        .all()
    ]
    programmes_list = [
        pg.to_dict()
        for pg in ProjectProgramme.query.filter_by(organization_id=org_id)
        .order_by(ProjectProgramme.id.desc())
        .all()
    ]
    intakes_list = [
        it.to_dict()
        for it in ProjectIntake.query.filter_by(organization_id=org_id)
        .order_by(ProjectIntake.weighted_score.desc(), ProjectIntake.id.desc())
        .all()
    ]

    from app.models.project_enterprise_batch3 import ProjectTemplate

    proj_templates_list = [
        pt.to_dict()
        for pt in ProjectTemplate.query.filter_by(organization_id=org_id)
        .order_by(ProjectTemplate.id.desc())
        .all()
    ]

    # UI-05 & UI-06: Server-side search, multi-facet filtering, deterministic sorting & pagination
    q_str = (request.args.get("q") or "").strip()
    f_cat = (request.args.get("category") or "ALL").strip()
    f_status = (request.args.get("status") or "ALL").strip()
    f_health = (request.args.get("health") or "ALL").strip()
    f_contracts = (request.args.get("contracts") or "ALL").strip()
    sort_by = (request.args.get("sort") or "updated").strip()
    sort_dir = (request.args.get("dir") or "desc").strip().lower()
    if sort_dir not in ("asc", "desc"):
        sort_dir = "desc"
    try:
        per_page = max(1, min(100, int(request.args.get("per_page") or 25)))
    except ValueError:
        per_page = 25
    try:
        page = max(1, int(request.args.get("page") or 1))
    except ValueError:
        page = 1

    filtered = []
    q_low = q_str.lower()
    for pc in project_cards:
        if f_cat != "ALL" and pc["category"] != f_cat:
            continue
        if f_status != "ALL" and pc["status"] != f_status:
            continue
        if f_health != "ALL" and pc["health"]["rag"] != f_health:
            continue
        if f_contracts == "with" and pc["contracts_total"] <= 0:
            continue
        if f_contracts == "free" and pc["contracts_total"] > 0:
            continue
        if q_low:
            hay = f"{pc['project_code']} {pc['name']} {pc.get('client_name') or ''} {pc['category']}".lower()
            if q_low not in hay:
                continue
        filtered.append(pc)

    def _sort_key(item):
        if sort_by == "name":
            return (item["name"].lower(), item["id"])
        if sort_by == "code":
            return (item["project_code"].lower(), item["id"])
        if sort_by == "budget":
            return (float(item["budget_amount"] or 0), item["id"])
        if sort_by == "health":
            return (int(item["health"]["score"]), item["id"])
        if sort_by == "progress":
            return (int(item["deliverables_pct"]), item["id"])
        return (item.get("created_at") or "", item["id"])

    filtered.sort(key=_sort_key, reverse=(sort_dir == "desc"))
    total_filtered = len(filtered)
    total_pages = max(1, (total_filtered + per_page - 1) // per_page)
    page = min(page, total_pages)
    start_idx = (page - 1) * per_page
    paged_projects = filtered[start_idx : start_idx + per_page]

    portfolio_prog = compute_deliverable_progress(all_delivs)
    return render_template(
        "contracts/projects.html",
        projects=paged_projects,
        all_projects_count=len(project_cards),
        categories=PROJECT_CATEGORIES,
        portfolios=portfolios_list,
        programmes=programmes_list,
        intakes=intakes_list,
        project_templates=proj_templates_list,
        filters={
            "q": q_str,
            "category": f_cat,
            "status": f_status,
            "health": f_health,
            "contracts": f_contracts,
            "sort": sort_by,
            "dir": sort_dir,
        },
        pager={
            "page": page,
            "per_page": per_page,
            "total": total_filtered,
            "total_pages": total_pages,
            "start": (start_idx + 1) if total_filtered else 0,
            "end": min(start_idx + per_page, total_filtered),
        },
        portfolio={
            "total_budget": total_budget,
            "total_committed": total_committed,
            "deliverables_pct": portfolio_prog["pct"],
            "deliverables_total": portfolio_prog["total"],
            "deliverables_accepted": portfolio_prog["accepted"],
            "probations_active": total_probations,
            "open_tasks": total_open_tasks,
            "open_risks": total_open_risks,
            "intakes_pending": sum(1 for i in intakes_list if i["status"] in ("submitted", "assessing")),
            "portfolios_count": len(portfolios_list),
            "programmes_count": len(programmes_list),
        },
    )


@contracts_views.route("/projects/<int:project_id>", methods=["GET"])
@login_required
def project_detail_page(project_id: int):
    actor = _actor()
    org_id = actor.organization_id
    ensure_contract_workflow_table()
    proj = Project.query.filter_by(id=project_id, organization_id=org_id).first()
    if proj is None:
        abort(404)
    wfs = ContractWorkflow.query.filter_by(organization_id=org_id, project_id=proj.id).all()
    doc_ids = [w.document_id for w in wfs]
    docs = {
        d.id: d
        for d in TSDocument.query.filter(TSDocument.id.in_(doc_ids)).all()
    } if doc_ids else {}
    wf_ids = [w.id for w in wfs]
    delivs = (
        ContractDeliverable.query.filter(
            ContractDeliverable.organization_id == org_id,
            ContractDeliverable.contract_id.in_(wf_ids),
        )
        .order_by(ContractDeliverable.due_date.asc(), ContractDeliverable.id.asc())
        .all()
        if wf_ids
        else []
    )
    kts = (
        ContractKeyTerm.query.filter(
            ContractKeyTerm.organization_id == org_id,
            ContractKeyTerm.contract_id.in_(wf_ids),
        )
        .order_by(ContractKeyTerm.id.asc())
        .all()
        if wf_ids
        else []
    )
    deliv_by_wf: dict[int, list[ContractDeliverable]] = {}
    for d in delivs:
        deliv_by_wf.setdefault(d.contract_id, []).append(d)
    wf_meta: dict[int, dict] = {}

    contracts = []
    all_proj_delivs = []
    committed_value = 0.0
    for w in wfs:
        d = docs.get(w.document_id)
        if not d or d.deleted_at:
            continue
        c_ref = w.contract_number or f"CTR-{d.id:04d}"
        c_url = f"/contracts/{d.id}/workflow"
        wf_meta[w.id] = {"contract_number": c_ref, "title": d.title, "url": c_url}
        c_delivs = deliv_by_wf.get(w.id, [])
        all_proj_delivs.extend(c_delivs)
        prog = compute_deliverable_progress(c_delivs)
        committed_value += _parse_num_val(w.deal_value)
        contracts.append({
            "document_id": d.id,
            "title": d.title,
            "contract_number": c_ref,
            "contract_type": w.contract_type,
            "contract_status": w.canonical_status(),
            "counterparty_name": w.counterparty_name or "—",
            "deal_value": f"{w.currency} {w.deal_value}" if w.deal_value else "—",
            "deliverables_pct": prog["pct"],
            "deliverables_total": prog["total"],
            "url": c_url,
        })

    deliverable_rows = [
        {**dl.to_dict(), **(wf_meta.get(dl.contract_id) or {})}
        for dl in delivs
        if dl.contract_id in wf_meta
    ]
    key_term_rows = [
        {**kt.to_dict(), **(wf_meta.get(kt.contract_id) or {})}
        for kt in kts
        if kt.contract_id in wf_meta
    ]
    from app.models.project_management import (
        ProjectRisk,
        ProjectTask,
        compute_project_health,
        ensure_project_management_tables,
    )

    ensure_project_management_tables()
    proj_tasks = (
        ProjectTask.query.filter_by(organization_id=org_id, project_id=proj.id)
        .order_by(ProjectTask.id.desc())
        .all()
    )
    proj_risks = (
        ProjectRisk.query.filter_by(organization_id=org_id, project_id=proj.id)
        .order_by(ProjectRisk.id.desc())
        .all()
    )
    task_rows = [
        {**t.to_dict(), "contract_number": (wf_meta.get(t.contract_id) or {}).get("contract_number", "")}
        for t in proj_tasks
    ]
    risk_rows = [
        {**r.to_dict(), "contract_number": (wf_meta.get(r.contract_id) or {}).get("contract_number", "")}
        for r in proj_risks
    ]
    util_pct = (
        min(150, int(round((committed_value / float(proj.budget_amount)) * 100)))
        if proj.budget_amount and float(proj.budget_amount) > 0
        else 0
    )
    susp_cnt = sum(1 for w in wfs if w.canonical_status() == "SUSPENDED")
    health = compute_project_health(
        budget_util_pct=util_pct,
        suspended_contracts=susp_cnt,
        tasks=proj_tasks,
        risks=proj_risks,
    )
    # Other org TSD Contracts available to link into this Project
    other_wfs = (
        ContractWorkflow.query.filter(
            ContractWorkflow.organization_id == org_id,
            ContractWorkflow.project_id != proj.id,
        )
        .order_by(ContractWorkflow.updated_at.desc())
        .limit(50)
        .all()
    )
    other_doc_ids = [w.document_id for w in other_wfs]
    other_docs = {
        d.id: d
        for d in TSDocument.query.filter(TSDocument.id.in_(other_doc_ids)).all()
    } if other_doc_ids else {}
    available_contracts = [
        {
            "document_id": w.document_id,
            "contract_number": w.contract_number or f"CTR-{w.document_id:04d}",
            "title": (other_docs.get(w.document_id).title if other_docs.get(w.document_id) else f"Contract #{w.document_id}"),
        }
        for w in other_wfs
        if other_docs.get(w.document_id) and not other_docs.get(w.document_id).deleted_at
    ]

    from app.models.project_management import (
        GATE_STAGES,
        LIFECYCLE_STATES,
        PROJECT_ROLES,
        ProjectBudgetLine,
        ProjectChangeRequest,
        ProjectCharter,
        ProjectCostEvent,
        ProjectGate,
        ProjectMembership,
        ProjectResourceAllocation,
        ProjectTaskDependency,
        ProjectTimeEntry,
        ProjectWBSNode,
    )
    from app.models.user import User
    from app.blueprints.projects.permissions import can_view_project_finance
    from app.blueprints.projects.services import (
        compute_project_financials,
        count_overallocated_resources,
    )

    show_finance = can_view_project_finance(proj, actor)
    charters = ProjectCharter.query.filter_by(organization_id=org_id, project_id=proj.id).order_by(ProjectCharter.version.desc()).all()
    gates_raw = ProjectGate.query.filter_by(organization_id=org_id, project_id=proj.id).all()
    gates_by_stage = {g.stage: g.to_dict() for g in gates_raw}
    gate_rows = [
        gates_by_stage.get(st, {"stage": st, "gate_state": "not_ready", "decision_note": ""})
        for st in GATE_STAGES
    ]
    wbs_nodes = [
        n.to_dict()
        for n in ProjectWBSNode.query.filter_by(organization_id=org_id, project_id=proj.id)
        .order_by(ProjectWBSNode.sort_order.asc(), ProjectWBSNode.id.asc())
        .all()
    ]
    task_deps = [
        d.to_dict()
        for d in ProjectTaskDependency.query.filter_by(organization_id=org_id, project_id=proj.id).all()
    ]
    alloc_rows = [
        a.to_dict(include_rates=show_finance)
        for a in ProjectResourceAllocation.query.filter_by(organization_id=org_id, project_id=proj.id)
        .order_by(ProjectResourceAllocation.id.desc())
        .all()
    ]
    time_rows = [
        te.to_dict(include_rates=show_finance)
        for te in ProjectTimeEntry.query.filter_by(organization_id=org_id, project_id=proj.id)
        .order_by(ProjectTimeEntry.work_date.desc(), ProjectTimeEntry.id.desc())
        .all()
    ]
    budget_lines = ProjectBudgetLine.query.filter_by(organization_id=org_id, project_id=proj.id).order_by(ProjectBudgetLine.id.asc()).all()
    cost_events = ProjectCostEvent.query.filter_by(organization_id=org_id, project_id=proj.id).order_by(ProjectCostEvent.id.desc()).all()
    financials = compute_project_financials(proj, budget_lines=budget_lines, cost_events=cost_events)
    change_rows = [
        c.to_dict()
        for c in ProjectChangeRequest.query.filter_by(organization_id=org_id, project_id=proj.id)
        .order_by(ProjectChangeRequest.id.desc())
        .all()
    ]
    org_users = User.query.filter_by(organization_id=org_id, is_active=True).order_by(User.username.asc()).all()
    user_map = {u.id: u for u in org_users}
    member_rows = [
        {
            **m.to_dict(),
            "username": user_map[m.user_id].username if m.user_id in user_map else f"User #{m.user_id}",
            "email": user_map[m.user_id].email if m.user_id in user_map else "",
        }
        for m in ProjectMembership.query.filter_by(organization_id=org_id, project_id=proj.id, is_active=True).all()
    ]
    overalloc = count_overallocated_resources(org_id, proj.id)
    eff_util = financials["budget_util_pct"] if financials["approved_budget"] > 0 else util_pct
    health = compute_project_health(
        budget_util_pct=eff_util,
        suspended_contracts=susp_cnt,
        tasks=proj_tasks,
        risks=proj_risks,
        available_budget=financials["available_budget"],
        approved_budget=financials["approved_budget"],
        overallocated_resources=overalloc,
    )

    from app.models.project_enterprise_ext import (
        ProjectAssetBooking,
        ProjectBacklogItem,
        ProjectBenefit,
        ProjectClosureItem,
        ProjectDocumentLink,
        ProjectIndicator,
        ProjectIndicatorObservation,
        ProjectProcurement,
        ProjectQualityRecord,
        ProjectRequirement,
        ProjectSprint,
        ProjectStakeholder,
    )

    req_rows = [r.to_dict() for r in ProjectRequirement.query.filter_by(organization_id=org_id, project_id=proj.id).order_by(ProjectRequirement.id.desc()).all()]
    sprint_rows = [s.to_dict() for s in ProjectSprint.query.filter_by(organization_id=org_id, project_id=proj.id).order_by(ProjectSprint.id.desc()).all()]
    backlog_rows = [b.to_dict() for b in ProjectBacklogItem.query.filter_by(organization_id=org_id, project_id=proj.id).order_by(ProjectBacklogItem.id.desc()).all()]
    asset_rows = [a.to_dict() for a in ProjectAssetBooking.query.filter_by(organization_id=org_id, project_id=proj.id).order_by(ProjectAssetBooking.id.desc()).all()]
    proc_rows = [pr.to_dict() for pr in ProjectProcurement.query.filter_by(organization_id=org_id, project_id=proj.id).order_by(ProjectProcurement.id.desc()).all()]
    qa_rows = [q.to_dict() for q in ProjectQualityRecord.query.filter_by(organization_id=org_id, project_id=proj.id).order_by(ProjectQualityRecord.id.desc()).all()]
    sh_rows = [sh.to_dict() for sh in ProjectStakeholder.query.filter_by(organization_id=org_id, project_id=proj.id).order_by(ProjectStakeholder.id.desc()).all()]
    doc_link_rows = [dl.to_dict() for dl in ProjectDocumentLink.query.filter_by(organization_id=org_id, project_id=proj.id).order_by(ProjectDocumentLink.id.desc()).all()]
    ind_rows = [i.to_dict() for i in ProjectIndicator.query.filter_by(organization_id=org_id, project_id=proj.id).order_by(ProjectIndicator.id.asc()).all()]
    obs_rows = [o.to_dict() for o in ProjectIndicatorObservation.query.filter_by(organization_id=org_id, project_id=proj.id).order_by(ProjectIndicatorObservation.id.desc()).all()]
    closure_rows = [ci.to_dict() for ci in ProjectClosureItem.query.filter_by(organization_id=org_id, project_id=proj.id).order_by(ProjectClosureItem.id.asc()).all()]
    benefit_rows = [bn.to_dict() for bn in ProjectBenefit.query.filter_by(organization_id=org_id, project_id=proj.id).order_by(ProjectBenefit.id.asc()).all()]

    from app.models.project_enterprise_batch3 import (
        ProjectApprovalRequest,
        ProjectComment,
        ProjectComplianceRecord,
        ProjectExternalGrant,
    )
    from app.blueprints.projects.permissions import can_approve_project_governance

    can_see_hse = can_approve_project_governance(proj, actor)
    comp_q = ProjectComplianceRecord.query.filter_by(organization_id=org_id, project_id=proj.id)
    if not can_see_hse:
        comp_q = comp_q.filter(ProjectComplianceRecord.is_restricted.is_(False))
    compliance_rows = [c.to_dict() for c in comp_q.order_by(ProjectComplianceRecord.id.desc()).all()]
    approval_rows = [a.to_dict() for a in ProjectApprovalRequest.query.filter_by(organization_id=org_id, project_id=proj.id).order_by(ProjectApprovalRequest.id.desc()).all()]
    comment_rows = [cm.to_dict() for cm in ProjectComment.query.filter_by(organization_id=org_id, project_id=proj.id).order_by(ProjectComment.id.desc()).all()]
    grant_rows = [g.to_dict() for g in ProjectExternalGrant.query.filter_by(organization_id=org_id, project_id=proj.id).order_by(ProjectExternalGrant.id.desc()).all()]

    from app.blueprints.projects.services import compute_critical_path, compute_project_evm

    cpm_schedule = compute_critical_path(proj)
    evm_metrics = compute_project_evm(proj, financials=financials)

    from app.models.contract_workflow import ContractObligation

    obligations_raw = (
        ContractObligation.query.filter(
            ContractObligation.organization_id == org_id,
            ContractObligation.contract_id.in_(wf_ids),
        )
        .order_by(ContractObligation.due_date.asc(), ContractObligation.id.asc())
        .all()
        if wf_ids
        else []
    )
    wf_doc_map = {w.id: w.document_id for w in wfs}
    obligation_rows = [
        {
            "id": ob.id,
            "contract_id": ob.contract_id,
            "document_id": wf_doc_map.get(ob.contract_id),
            "contract_number": (wf_meta.get(ob.contract_id) or {}).get("contract_number", ""),
            "contract_url": (wf_meta.get(ob.contract_id) or {}).get("url", "#"),
            "title": ob.title,
            "category": ob.category or "general",
            "owner_name": ob.owner_name or "Unassigned",
            "due_date": ob.due_date or "—",
            "status": ob.status or "open",
        }
        for ob in obligations_raw
        if ob.contract_id in wf_meta
    ]

    all_org_projects = [
        {"id": p.id, "project_code": p.project_code, "name": p.name}
        for p in Project.query.filter_by(organization_id=org_id).order_by(Project.updated_at.desc()).limit(50).all()
    ]

    overall_prog = compute_deliverable_progress(all_proj_delivs)
    templates = ensure_default_templates(org_id, actor)
    return render_template(
        "contracts/project_detail.html",
        project=proj.to_dict(),
        all_org_projects=all_org_projects,
        obligation_rows=obligation_rows,
        contracts=contracts,
        deliverable_rows=deliverable_rows,
        key_term_rows=key_term_rows,
        task_rows=task_rows,
        risk_rows=risk_rows,
        health=health,
        budget_util_pct=eff_util,
        available_contracts=available_contracts,
        categories=PROJECT_CATEGORIES,
        committed_value=committed_value,
        overall_prog=overall_prog,
        templates=[t.to_dict() for t in templates if t.state == "published"],
        charter=charters[0].to_dict() if charters else None,
        gate_rows=gate_rows,
        lifecycle_states=LIFECYCLE_STATES,
        wbs_nodes=wbs_nodes,
        task_deps=task_deps,
        cpm_schedule=cpm_schedule,
        evm_metrics=evm_metrics,
        alloc_rows=alloc_rows,
        time_rows=time_rows,
        budget_lines=[b.to_dict() for b in budget_lines],
        cost_events=[e.to_dict() for e in cost_events],
        financials=financials,
        change_rows=change_rows,
        member_rows=member_rows,
        org_users=[{"id": u.id, "username": u.username, "email": u.email} for u in org_users],
        project_roles=PROJECT_ROLES,
        show_finance=show_finance,
        req_rows=req_rows,
        sprint_rows=sprint_rows,
        backlog_rows=backlog_rows,
        asset_rows=asset_rows,
        proc_rows=proc_rows,
        qa_rows=qa_rows,
        sh_rows=sh_rows,
        doc_link_rows=doc_link_rows,
        ind_rows=ind_rows,
        obs_rows=obs_rows,
        closure_rows=closure_rows,
        benefit_rows=benefit_rows,
        compliance_rows=compliance_rows,
        approval_rows=approval_rows,
        comment_rows=comment_rows,
        grant_rows=grant_rows,
    )


@contracts_views.route("/contracts/templates", methods=["GET"])
@login_required
def contract_templates_page():
    actor = _actor()
    org_id = actor.organization_id
    ensure_contract_workflow_table()
    ensure_default_project(org_id, actor)
    templates = ensure_default_templates(org_id, actor)
    projects = (
        Project.query.filter_by(organization_id=org_id)
        .order_by(Project.is_default.desc(), Project.name.asc())
        .all()
    )
    return render_template(
        "contracts/templates_studio.html",
        templates=[t.to_dict() for t in templates],
        projects=[p.to_dict() for p in projects],
        contract_types=CONTRACT_TYPES,
        categories=PROJECT_CATEGORIES,
    )


@contracts_views.route("/my-work", methods=["GET"])
@login_required
def my_work_page():
    """PM-13.03 & PM-23: Personal Work Inbox & Consolidated Weekly Timesheet Grid."""
    from datetime import date, timedelta
    from decimal import Decimal
    from app.models.project_enterprise_batch3 import ProjectApprovalRequest
    from app.models.project_management import ProjectTask, ProjectTimeEntry

    actor = _actor()
    org_id = actor.organization_id
    ensure_contract_workflow_table()
    ensure_default_project(org_id, actor)

    projs = Project.query.filter_by(organization_id=org_id).order_by(Project.updated_at.desc()).all()
    proj_map = {p.id: p for p in projs}

    today = date.today()
    monday = today - timedelta(days=today.weekday())
    week_dates = [monday + timedelta(days=i) for i in range(7)]
    week_days = [
        {"iso": d.isoformat(), "label": d.strftime("%a"), "short": d.strftime("%d %b")}
        for d in week_dates
    ]

    entries = ProjectTimeEntry.query.filter(
        ProjectTimeEntry.organization_id == org_id,
        ProjectTimeEntry.user_id == actor.id,
        ProjectTimeEntry.work_date >= week_dates[0],
        ProjectTimeEntry.work_date <= week_dates[-1],
    ).all()

    by_proj_day: dict[int, dict[date, Decimal]] = {}
    for e in entries:
        by_proj_day.setdefault(e.project_id, {})
        by_proj_day[e.project_id][e.work_date] = by_proj_day[e.project_id].get(e.work_date, Decimal("0.00")) + Decimal(e.hours or 0)

    daily_totals = [Decimal("0.00")] * 7
    grid_rows = []
    for pid, dmap in by_proj_day.items():
        p = proj_map.get(pid)
        if not p:
            continue
        cells = []
        row_tot = Decimal("0.00")
        for idx, wd in enumerate(week_dates):
            v = dmap.get(wd, Decimal("0.00"))
            cells.append(float(v))
            row_tot += v
            daily_totals[idx] += v
        grid_rows.append({
            "project_id": p.id,
            "project_code": p.project_code,
            "project_name": p.name,
            "cells": cells,
            "total": float(row_tot),
        })

    week_total = sum(daily_totals, Decimal("0.00"))
    my_tasks_raw = ProjectTask.query.filter_by(organization_id=org_id, assignee_user_id=actor.id).filter(ProjectTask.status != "done").order_by(ProjectTask.id.desc()).all()
    my_tasks = [
        {**t.to_dict(), "project_name": proj_map[t.project_id].name if t.project_id in proj_map else f"Project #{t.project_id}"}
        for t in my_tasks_raw
    ]
    pending_approvals = [
        a.to_dict()
        for a in ProjectApprovalRequest.query.filter_by(organization_id=org_id, status="pending")
        .filter(ProjectApprovalRequest.requested_by_id != actor.id)
        .order_by(ProjectApprovalRequest.id.desc())
        .all()
    ]

    return render_template(
        "contracts/my_work.html",
        my_projects=[p.to_dict() for p in projs],
        week_days=week_days,
        grid_rows=grid_rows,
        daily_totals=[float(x) for x in daily_totals],
        week_total_hours=str(week_total.quantize(Decimal("0.01"))),
        today_iso=today.isoformat(),
        my_tasks=my_tasks,
        pending_approvals=pending_approvals,
    )
