"""HTML views for Projects Hub and Contract Templates Studio."""
from __future__ import annotations

from flask import Blueprint, abort, render_template
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

    portfolio_prog = compute_deliverable_progress(all_delivs)
    return render_template(
        "contracts/projects.html",
        projects=project_cards,
        categories=PROJECT_CATEGORIES,
        portfolio={
            "total_budget": total_budget,
            "total_committed": total_committed,
            "deliverables_pct": portfolio_prog["pct"],
            "deliverables_total": portfolio_prog["total"],
            "deliverables_accepted": portfolio_prog["accepted"],
            "probations_active": total_probations,
            "open_tasks": total_open_tasks,
            "open_risks": total_open_risks,
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

    overall_prog = compute_deliverable_progress(all_proj_delivs)
    templates = ensure_default_templates(org_id, actor)
    return render_template(
        "contracts/project_detail.html",
        project=proj.to_dict(),
        contracts=contracts,
        deliverable_rows=deliverable_rows,
        key_term_rows=key_term_rows,
        task_rows=task_rows,
        risk_rows=risk_rows,
        health=health,
        budget_util_pct=util_pct,
        available_contracts=available_contracts,
        categories=PROJECT_CATEGORIES,
        committed_value=committed_value,
        overall_prog=overall_prog,
        templates=[t.to_dict() for t in templates if t.state == "published"],
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
