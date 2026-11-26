"""REST APIs for Projects, Contract Templates, and the unified Contracts CLM module.

All routes are tenant-scoped to ``current_user.organization_id`` and emit
chained-hash ``SecurityEvent`` entries on mutations.
"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timedelta

from flask import Blueprint, Response, abort, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy.orm.attributes import flag_modified

from app.extensions import db
from app.models.clause import Clause, ClauseVersion
from app.models.contract_workflow import (
    ContractDeliverable,
    ContractKeyTerm,
    ContractObligation,
    ContractTemplate,
    ContractWorkflow,
    Project,
    ensure_contract_workflow_table,
)
from app.models.tsd_approval import TSDApproval
from app.models.tsd_comment import TSDComment
from app.models.tsd_document import TSDocument
from app.models.tsd_document_version import TSDocumentVersion
from app.models.tsd_external_share import TSDExternalShare, hash_token, new_token
from app.models.user import User
from app.services.tsd_format import decrypt_content_envelope, serialize_container
from app.blueprints.contracts.lifecycle_service import (
    actor_label,
    append_workflow_event,
    apply_letterhead_to_contract,
    apply_template_to_contract,
    close_and_seal_contract,
    compute_deliverable_progress,
    compute_version_diff,
    create_linked_contract,
    emit_contract_security_event,
    ensure_default_approved_clauses,
    ensure_default_project,
    ensure_default_templates,
    extract_external_contract_details,
    file_external_signed_contract,
    get_or_create_workflow,
    instantiate_contract_from_template,
    render_contract_pdf,
    resume_contract,
    save_contract_html,
    suspend_contract,
    terminate_contract_record,
    transition_stage,
)


contracts_api = Blueprint("contracts_api", __name__, url_prefix="/api/contracts")
projects_api = Blueprint("projects_api", __name__, url_prefix="/api/projects")
contract_templates_api = Blueprint(
    "contract_templates_api", __name__, url_prefix="/api/contract-templates"
)


def _actor():
    if not current_user.is_authenticated:
        abort(401)
    if current_user.organization_id is None:
        abort(403, description="organization_required")
    return current_user


def _owned_doc(doc_id: int) -> tuple[TSDocument, ContractWorkflow, User]:
    actor = _actor()
    doc = (
        TSDocument.query.filter_by(id=doc_id, organization_id=actor.organization_id)
        .filter(TSDocument.deleted_at.is_(None))
        .first()
    )
    if doc is None:
        abort(404)
    wf = get_or_create_workflow(doc, actor)
    return doc, wf, actor


# =====================================================================
# 1. PROJECTS API (/api/projects)
# =====================================================================

@projects_api.route("", methods=["GET"])
@projects_api.route("/", methods=["GET"])
@login_required
def list_projects():
    actor = _actor()
    org_id = actor.organization_id
    ensure_contract_workflow_table()
    ensure_default_project(org_id, actor)

    projects = (
        Project.query.filter_by(organization_id=org_id)
        .order_by(Project.is_default.desc(), Project.updated_at.desc())
        .all()
    )
    wfs = ContractWorkflow.query.filter_by(organization_id=org_id).all()
    delivs = ContractDeliverable.query.filter_by(organization_id=org_id).all()
    deliv_by_wf: dict[int, list[ContractDeliverable]] = {}
    for d in delivs:
        deliv_by_wf.setdefault(d.contract_id, []).append(d)

    out = []
    for p in projects:
        p_wfs = [w for w in wfs if w.project_id == p.id]
        p_delivs = [d for w in p_wfs for d in deliv_by_wf.get(w.id, [])]
        prog = compute_deliverable_progress(p_delivs)
        out.append({
            **p.to_dict(),
            "contracts_total": len(p_wfs),
            "contracts_signed": sum(1 for w in p_wfs if w.canonical_status() == "SIGNED"),
            "contracts_draft": sum(1 for w in p_wfs if w.canonical_status() == "DRAFT"),
            "contracts_suspended": sum(1 for w in p_wfs if w.canonical_status() == "SUSPENDED"),
            "contracts_terminated": sum(1 for w in p_wfs if w.canonical_status() == "TERMINATED"),
            "deliverable_progress": prog,
        })
    return jsonify({"ok": True, "projects": out})


@projects_api.route("", methods=["POST"])
@projects_api.route("/", methods=["POST"])
@login_required
def create_project():
    actor = _actor()
    org_id = actor.organization_id
    ensure_contract_workflow_table()
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()[:200]
    if not name:
        return jsonify({"error": "Project name is required"}), 400

    existing_cnt = Project.query.filter_by(organization_id=org_id).count()
    code = str(data.get("project_code") or f"PRJ-{datetime.utcnow().year}-{existing_cnt + 1:03d}").strip()[:40]
    budget = None
    if data.get("budget_amount") not in (None, ""):
        try:
            budget = float(data["budget_amount"])
        except (TypeError, ValueError):
            pass

    proj = Project(
        organization_id=org_id,
        project_code=code,
        name=name,
        description=str(data.get("description") or "").strip() or None,
        category=str(data.get("category") or "client_delivery").strip()[:48],
        client_name=str(data.get("client_name") or "").strip()[:200] or None,
        owner_user_id=actor.id,
        status=str(data.get("status") or "active").strip()[:24],
        budget_amount=budget,
        currency=str(data.get("currency") or "USD").strip()[:12],
        start_date=str(data.get("start_date") or "").strip()[:32] or None,
        end_date=str(data.get("end_date") or "").strip()[:32] or None,
        is_default=False,
    )
    db.session.add(proj)
    db.session.flush()
    emit_contract_security_event(
        organization_id=org_id,
        actor_id=actor.id,
        action="project.created",
        document_id=proj.id,
    )
    db.session.commit()
    return jsonify({"ok": True, "project": proj.to_dict()}), 201


@projects_api.route("/<int:project_id>", methods=["GET", "PATCH"])
@login_required
def project_detail(project_id: int):
    actor = _actor()
    org_id = actor.organization_id
    proj = Project.query.filter_by(id=project_id, organization_id=org_id).first()
    if proj is None:
        abort(404)

    if request.method == "PATCH":
        data = request.get_json(silent=True) or {}
        for field, limit in (
            ("name", 200),
            ("description", 2000),
            ("category", 48),
            ("client_name", 200),
            ("status", 24),
            ("currency", 12),
            ("start_date", 32),
            ("end_date", 32),
        ):
            if field in data:
                setattr(proj, field, str(data.get(field) or "").strip()[:limit] or None)
        if "budget_amount" in data:
            val = data.get("budget_amount")
            proj.budget_amount = float(val) if val not in (None, "") else None
        db.session.commit()
        return jsonify({"ok": True, "project": proj.to_dict()})

    wfs = ContractWorkflow.query.filter_by(organization_id=org_id, project_id=proj.id).all()
    doc_ids = [w.document_id for w in wfs]
    docs = {
        d.id: d
        for d in TSDocument.query.filter(TSDocument.id.in_(doc_ids)).all()
    } if doc_ids else {}
    contracts = []
    for w in wfs:
        d = docs.get(w.document_id)
        if not d or d.deleted_at:
            continue
        delivs = ContractDeliverable.query.filter_by(contract_id=w.id, organization_id=org_id).all()
        contracts.append({
            "document_id": d.id,
            "title": d.title,
            "contract_number": w.contract_number or f"CTR-{d.id:04d}",
            "contract_type": w.contract_type,
            "contract_status": w.canonical_status(),
            "counterparty_name": w.counterparty_name or "",
            "deal_value": f"{w.currency} {w.deal_value}" if w.deal_value else "",
            "deliverable_progress": compute_deliverable_progress(delivs),
            "url": f"/contracts/{d.id}/workflow",
        })
    return jsonify({"ok": True, "project": proj.to_dict(), "contracts": contracts})


@projects_api.route("/<int:project_id>/link-contract", methods=["POST"])
@login_required
def link_contract_to_project(project_id: int):
    actor = _actor()
    org_id = actor.organization_id
    proj = Project.query.filter_by(id=project_id, organization_id=org_id).first()
    if proj is None:
        abort(404)
    data = request.get_json(silent=True) or {}
    doc_id = data.get("document_id")
    if not doc_id:
        return jsonify({"error": "document_id is required"}), 400
    wf = ContractWorkflow.query.filter_by(document_id=int(doc_id), organization_id=org_id).first()
    if wf is None:
        return jsonify({"error": "Contract not found in organization"}), 404
    wf.project_id = proj.id
    emit_contract_security_event(
        organization_id=org_id,
        actor_id=actor.id,
        action="project.contract_linked",
        document_id=wf.document_id,
    )
    db.session.commit()
    return jsonify({"ok": True, "project_id": proj.id, "document_id": wf.document_id})


@projects_api.route("/<int:project_id>/tasks", methods=["GET", "POST"])
@login_required
def project_tasks_collection(project_id: int):
    from app.models.project_management import (
        ProjectTask,
        TASK_PRIORITIES,
        TASK_STATUSES,
        ensure_project_management_tables,
    )

    ensure_project_management_tables()
    actor = _actor()
    org_id = actor.organization_id
    proj = Project.query.filter_by(id=project_id, organization_id=org_id).first()
    if proj is None:
        abort(404)

    if request.method == "GET":
        rows = (
            ProjectTask.query.filter_by(organization_id=org_id, project_id=proj.id)
            .order_by(ProjectTask.id.desc())
            .all()
        )
        return jsonify({"ok": True, "tasks": [r.to_dict() for r in rows]})

    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()[:220]
    if not title:
        return jsonify({"error": "Task title is required"}), 400
    priority = str(data.get("priority") or "medium").strip().lower()
    if priority not in TASK_PRIORITIES:
        priority = "medium"
    status = str(data.get("status") or "todo").strip().lower()
    if status not in TASK_STATUSES:
        status = "todo"
    cid = data.get("contract_id")
    contract_id = int(cid) if str(cid or "").isdigit() else None
    t = ProjectTask(
        organization_id=org_id,
        project_id=proj.id,
        contract_id=contract_id,
        title=title,
        description=str(data.get("description") or "").strip() or None,
        phase=str(data.get("phase") or "Execution").strip()[:64],
        assignee_name=str(data.get("assignee_name") or "").strip()[:120] or None,
        priority=priority,
        status=status,
        due_date=str(data.get("due_date") or "").strip()[:32] or None,
        progress_pct=100 if status == "done" else int(data.get("progress_pct") or 0),
        created_by_id=actor.id,
    )
    db.session.add(t)
    db.session.commit()
    return jsonify({"ok": True, "task": t.to_dict()}), 201


@projects_api.route("/<int:project_id>/tasks/<int:task_id>", methods=["PATCH", "DELETE"])
@login_required
def project_task_item(project_id: int, task_id: int):
    from app.models.project_management import (
        ProjectTask,
        TASK_PRIORITIES,
        TASK_STATUSES,
        ensure_project_management_tables,
    )

    ensure_project_management_tables()
    actor = _actor()
    org_id = actor.organization_id
    t = ProjectTask.query.filter_by(id=task_id, project_id=project_id, organization_id=org_id).first()
    if t is None:
        abort(404)

    if request.method == "DELETE":
        db.session.delete(t)
        db.session.commit()
        return jsonify({"ok": True, "deleted": task_id})

    data = request.get_json(silent=True) or {}
    if "title" in data and str(data["title"]).strip():
        t.title = str(data["title"]).strip()[:220]
    if "description" in data:
        t.description = str(data["description"] or "").strip() or None
    if "phase" in data:
        t.phase = str(data["phase"] or "Execution").strip()[:64]
    if "assignee_name" in data:
        t.assignee_name = str(data["assignee_name"] or "").strip()[:120] or None
    if "due_date" in data:
        t.due_date = str(data["due_date"] or "").strip()[:32] or None
    if "priority" in data and str(data["priority"]).lower() in TASK_PRIORITIES:
        t.priority = str(data["priority"]).lower()
    if "status" in data and str(data["status"]).lower() in TASK_STATUSES:
        t.status = str(data["status"]).lower()
        if t.status == "done":
            t.progress_pct = 100
        elif t.status == "in_progress" and (t.progress_pct or 0) == 0:
            t.progress_pct = 50
        elif t.status == "todo":
            t.progress_pct = 0
    if "progress_pct" in data:
        try:
            t.progress_pct = max(0, min(100, int(data["progress_pct"])))
        except (TypeError, ValueError):
            pass
    db.session.commit()
    return jsonify({"ok": True, "task": t.to_dict()})


@projects_api.route("/<int:project_id>/risks", methods=["GET", "POST"])
@login_required
def project_risks_collection(project_id: int):
    from app.models.project_management import (
        ProjectRisk,
        RISK_CATEGORIES,
        RISK_SEVERITIES,
        RISK_STATUSES,
        ensure_project_management_tables,
    )

    ensure_project_management_tables()
    actor = _actor()
    org_id = actor.organization_id
    proj = Project.query.filter_by(id=project_id, organization_id=org_id).first()
    if proj is None:
        abort(404)

    if request.method == "GET":
        rows = (
            ProjectRisk.query.filter_by(organization_id=org_id, project_id=proj.id)
            .order_by(ProjectRisk.id.desc())
            .all()
        )
        return jsonify({"ok": True, "risks": [r.to_dict() for r in rows]})

    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()[:220]
    if not title:
        return jsonify({"error": "Risk title is required"}), 400
    cat = str(data.get("category") or "contractual").strip().lower()
    if cat not in RISK_CATEGORIES:
        cat = "contractual"
    sev = str(data.get("severity") or "medium").strip().lower()
    if sev not in RISK_SEVERITIES:
        sev = "medium"
    lik = str(data.get("likelihood") or "medium").strip().lower()
    if lik not in ("low", "medium", "high"):
        lik = "medium"
    st = str(data.get("status") or "open").strip().lower()
    if st not in RISK_STATUSES:
        st = "open"
    cid = data.get("contract_id")
    contract_id = int(cid) if str(cid or "").isdigit() else None
    r = ProjectRisk(
        organization_id=org_id,
        project_id=proj.id,
        contract_id=contract_id,
        title=title,
        category=cat,
        severity=sev,
        likelihood=lik,
        mitigation_plan=str(data.get("mitigation_plan") or "").strip() or None,
        owner_name=str(data.get("owner_name") or "").strip()[:120] or None,
        status=st,
        created_by_id=actor.id,
    )
    db.session.add(r)
    db.session.commit()
    return jsonify({"ok": True, "risk": r.to_dict()}), 201


@projects_api.route("/<int:project_id>/risks/<int:risk_id>", methods=["PATCH", "DELETE"])
@login_required
def project_risk_item(project_id: int, risk_id: int):
    from app.models.project_management import (
        ProjectRisk,
        RISK_SEVERITIES,
        RISK_STATUSES,
        ensure_project_management_tables,
    )

    ensure_project_management_tables()
    actor = _actor()
    org_id = actor.organization_id
    r = ProjectRisk.query.filter_by(id=risk_id, project_id=project_id, organization_id=org_id).first()
    if r is None:
        abort(404)

    if request.method == "DELETE":
        db.session.delete(r)
        db.session.commit()
        return jsonify({"ok": True, "deleted": risk_id})

    data = request.get_json(silent=True) or {}
    if "status" in data and str(data["status"]).lower() in RISK_STATUSES:
        r.status = str(data["status"]).lower()
    if "severity" in data and str(data["severity"]).lower() in RISK_SEVERITIES:
        r.severity = str(data["severity"]).lower()
    if "mitigation_plan" in data:
        r.mitigation_plan = str(data["mitigation_plan"] or "").strip() or None
    if "owner_name" in data:
        r.owner_name = str(data["owner_name"] or "").strip()[:120] or None
    db.session.commit()
    return jsonify({"ok": True, "risk": r.to_dict()})


# =====================================================================
# 2. CONTRACT TEMPLATES API (/api/contract-templates)
# =====================================================================

@contract_templates_api.route("", methods=["GET"])
@contract_templates_api.route("/", methods=["GET"])
@login_required
def list_contract_templates():
    actor = _actor()
    org_id = actor.organization_id
    ensure_contract_workflow_table()
    rows = ensure_default_templates(org_id, actor)
    state_f = (request.args.get("state") or "").strip().lower()
    type_f = (request.args.get("contract_type") or "").strip().lower()
    out = []
    for t in rows:
        if state_f and t.state != state_f:
            continue
        if type_f and t.contract_type != type_f:
            continue
        out.append(t.to_dict())
    return jsonify({"ok": True, "templates": out})


@contract_templates_api.route("", methods=["POST"])
@contract_templates_api.route("/", methods=["POST"])
@login_required
def create_contract_template():
    actor = _actor()
    org_id = actor.organization_id
    ensure_contract_workflow_table()
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()[:200]
    if not name:
        return jsonify({"error": "Template name is required"}), 400
    tpl = ContractTemplate(
        organization_id=org_id,
        name=name,
        description=str(data.get("description") or "").strip()[:500] or None,
        contract_type=str(data.get("contract_type") or "msa").strip()[:48],
        default_project_category=str(data.get("default_project_category") or "client_delivery").strip()[:48],
        state="draft",
        version=1,
        body_html=str(data.get("body_html") or f"<h1>{name}</h1><p>Contract terms between Organization and {{{{counterparty_name}}}}.</p>"),
        variables_json=data.get("variables") if isinstance(data.get("variables"), list) else [],
        default_key_terms_json=data.get("default_key_terms") if isinstance(data.get("default_key_terms"), list) else [],
        default_deliverables_json=data.get("default_deliverables") if isinstance(data.get("default_deliverables"), list) else [],
        policy_json=data.get("policy") if isinstance(data.get("policy"), dict) else {"routing_mode": "parallel"},
        created_by_id=actor.id,
    )
    db.session.add(tpl)
    db.session.commit()
    return jsonify({"ok": True, "template": tpl.to_dict()}), 201


@contract_templates_api.route("/<int:tpl_id>/publish", methods=["POST"])
@login_required
def publish_contract_template(tpl_id: int):
    actor = _actor()
    tpl = ContractTemplate.query.filter_by(id=tpl_id, organization_id=actor.organization_id).first()
    if tpl is None:
        abort(404)
    tpl.state = "published"
    tpl.published_at = datetime.utcnow()
    emit_contract_security_event(
        organization_id=actor.organization_id,
        actor_id=actor.id,
        action="contract_template.published",
        document_id=tpl.id,
    )
    db.session.commit()
    return jsonify({"ok": True, "template": tpl.to_dict()})


@contract_templates_api.route("/<int:tpl_id>/instantiate", methods=["POST"])
@login_required
def instantiate_template(tpl_id: int):
    actor = _actor()
    org_id = actor.organization_id
    tpl = ContractTemplate.query.filter_by(id=tpl_id, organization_id=org_id).first()
    if tpl is None:
        abort(404)
    if tpl.state != "published":
        return jsonify({"error": "Only published templates can be instantiated into contracts."}), 400
    data = request.get_json(silent=True) or {}
    project_id = data.get("project_id")
    if project_id:
        proj = Project.query.filter_by(id=int(project_id), organization_id=org_id).first()
        if proj is None:
            return jsonify({"error": "Selected project not found"}), 404
    else:
        proj = ensure_default_project(org_id, actor)

    title = str(data.get("title") or "").strip()
    variables = data.get("variables") if isinstance(data.get("variables"), dict) else {}
    doc, wf = instantiate_contract_from_template(
        template=tpl, project=proj, actor=actor, title=title, variables=variables
    )
    return jsonify({
        "ok": True,
        "document_id": doc.id,
        "contract_number": wf.contract_number,
        "project_id": proj.id,
        "workflow": wf.to_dict(),
        "url": f"/contracts/{doc.id}/workflow",
    }), 201


@contract_templates_api.route("/catalog", methods=["GET"])
@login_required
def search_template_catalog():
    """Search & paginate the 1,050+ full-length system Contract Templates library."""
    _actor()
    from app.models.contract_templates_catalog import search_catalog_templates

    res = search_catalog_templates(
        q=request.args.get("q") or "",
        category=request.args.get("category") or "",
        contract_type=request.args.get("contract_type") or "",
        page=int(request.args.get("page") or 1),
        per_page=int(request.args.get("per_page") or 24),
    )
    return jsonify({"ok": True, **res})


@contract_templates_api.route("/catalog/<slug>", methods=["GET"])
@login_required
def get_catalog_template_detail(slug: str):
    """Return full 14-article HTML preview and blueprint metadata for any catalog template."""
    _actor()
    from app.models.contract_templates_catalog import (
        get_catalog_index_by_slug,
        render_catalog_template_html,
    )

    item = get_catalog_index_by_slug().get(slug)
    if item is None:
        return jsonify({"error": "Catalog template not found"}), 404
    return jsonify({
        "ok": True,
        "template": {
            **item,
            "body_html": render_catalog_template_html(item),
        },
    })


def _materialize_catalog_template(slug: str, org_id: int, actor) -> ContractTemplate | None:
    """Resolve a 1,050+ catalog slug into a reusable org ContractTemplate row (idempotent)."""
    from app.models.contract_templates_catalog import (
        get_catalog_index_by_slug,
        render_catalog_template_html,
    )

    item = get_catalog_index_by_slug().get(slug)
    if item is None:
        return None
    existing = ContractTemplate.query.filter_by(
        organization_id=org_id, name=item["name"]
    ).first()
    if existing is not None:
        return existing
    tpl = ContractTemplate(
        organization_id=org_id,
        name=item["name"][:200],
        description=item["description"][:500],
        contract_type=item["contract_type"][:48],
        default_project_category=item["default_project_category"][:48],
        state="published",
        version=1,
        body_html=render_catalog_template_html(item),
        variables_json=["project_name", "project_code", "counterparty_name", "deal_value", "currency", "effective_date", "expiration_date", "governing_law"],
        default_key_terms_json=item["default_key_terms"],
        default_deliverables_json=item["default_deliverables"],
        policy_json={"routing_mode": "parallel", "catalog_slug": slug, "category": item["category"]},
        created_by_id=actor.id,
        published_at=datetime.utcnow(),
    )
    db.session.add(tpl)
    db.session.flush()
    return tpl


@contract_templates_api.route("/catalog/<slug>/instantiate", methods=["POST"])
@login_required
def instantiate_catalog_template(slug: str):
    """Instantiate any of the 1,050+ full-length catalog templates directly into a Project."""
    actor = _actor()
    org_id = actor.organization_id
    ensure_contract_workflow_table()
    tpl = _materialize_catalog_template(slug, org_id, actor)
    if tpl is None:
        return jsonify({"error": "Catalog template not found"}), 404

    data = request.get_json(silent=True) or {}
    project_id = data.get("project_id")
    if project_id:
        proj = Project.query.filter_by(id=int(project_id), organization_id=org_id).first()
        if proj is None:
            return jsonify({"error": "Selected project not found"}), 404
    else:
        proj = ensure_default_project(org_id, actor)

    title = str(data.get("title") or "").strip()
    variables = data.get("variables") if isinstance(data.get("variables"), dict) else {}
    doc, wf = instantiate_contract_from_template(
        template=tpl, project=proj, actor=actor, title=title, variables=variables
    )
    return jsonify({
        "ok": True,
        "document_id": doc.id,
        "contract_number": wf.contract_number,
        "project_id": proj.id,
        "workflow": wf.to_dict(),
        "url": f"/contracts/{doc.id}/workflow",
    }), 201


# =====================================================================
# 3. CONTRACTS CLM API (/api/contracts)
# =====================================================================

_MAX_EXTERNAL_CONTRACT_BYTES = 15 * 1024 * 1024  # 15 MB


@contracts_api.route("/extract", methods=["POST"])
@login_required
def extract_external_contract():
    """Extract metadata & readable text preview from an uploaded external signed contract."""
    _actor()
    f = request.files.get("file")
    if f is None or not f.filename:
        return jsonify({"error": "Please attach a signed contract file (.pdf, .docx, or .txt)."}), 400
    raw = f.read(_MAX_EXTERNAL_CONTRACT_BYTES + 1)
    if not raw:
        return jsonify({"error": "Uploaded file is empty."}), 400
    if len(raw) > _MAX_EXTERNAL_CONTRACT_BYTES:
        return jsonify({"error": "File exceeds maximum size of 15 MB."}), 413
    extracted = extract_external_contract_details(raw, f.filename)
    extracted.pop("html_body", None)
    return jsonify({"ok": True, "extracted": extracted})


@contracts_api.route("/upload", methods=["POST"])
@login_required
def upload_external_contract():
    """Upload, archive, and file an already-signed external contract into a Project & Evidence Vault."""
    actor = _actor()
    org_id = actor.organization_id
    ensure_contract_workflow_table()

    f = request.files.get("file")
    if f is None or not f.filename:
        return jsonify({"error": "Please attach a signed contract file (.pdf, .docx, or .txt)."}), 400
    raw = f.read(_MAX_EXTERNAL_CONTRACT_BYTES + 1)
    if not raw:
        return jsonify({"error": "Uploaded file is empty."}), 400
    if len(raw) > _MAX_EXTERNAL_CONTRACT_BYTES:
        return jsonify({"error": "File exceeds maximum size of 15 MB."}), 413

    form = request.form
    proj_id_raw = form.get("project_id")
    if proj_id_raw:
        proj = Project.query.filter_by(id=int(proj_id_raw), organization_id=org_id).first()
        if proj is None:
            return jsonify({"error": "Selected project not found."}), 404
    else:
        proj = ensure_default_project(org_id, actor)

    meta = {
        "title": form.get("title"),
        "contract_type": form.get("contract_type"),
        "counterparty_name": form.get("counterparty_name"),
        "currency": form.get("currency"),
        "deal_value": form.get("deal_value"),
        "effective_date": form.get("effective_date"),
        "expiration_date": form.get("expiration_date"),
        "governing_law": form.get("governing_law"),
        "contract_status": form.get("contract_status") or "SIGNED",
        "signatories": form.get("signatories"),
        "probation_days": form.get("probation_days"),
        "notes": form.get("notes"),
    }
    doc, wf = file_external_signed_contract(
        file_bytes=raw,
        filename=f.filename,
        project=proj,
        actor=actor,
        meta=meta,
    )
    return jsonify({
        "ok": True,
        "document_id": doc.id,
        "contract_number": wf.contract_number,
        "project_id": proj.id,
        "contract_status": wf.contract_status,
        "evidence_retention_id": wf.evidence_retention_id,
        "execution_sha256": wf.execution_sha256,
        "url": f"/contracts/{doc.id}/workflow",
    }), 201


@contracts_api.route("/<int:doc_id>/state", methods=["GET"])
@login_required
def get_contract_state(doc_id: int):
    doc, wf, actor = _owned_doc(doc_id)
    org_id = actor.organization_id

    env = decrypt_content_envelope(doc.ciphertext, organization_id=org_id) or {}
    html_body = env.get("html") or ""

    project = db.session.get(Project, wf.project_id) if wf.project_id else None
    all_projects = [
        p.to_dict()
        for p in Project.query.filter_by(organization_id=org_id)
        .order_by(Project.is_default.desc(), Project.name.asc())
        .all()
    ]

    key_terms = [
        kt.to_dict()
        for kt in ContractKeyTerm.query.filter_by(contract_id=wf.id, organization_id=org_id)
        .order_by(ContractKeyTerm.id.asc())
        .all()
    ]
    probation_term = next((kt for kt in key_terms if kt["category"] == "probation"), None)

    deliv_rows = (
        ContractDeliverable.query.filter_by(contract_id=wf.id, organization_id=org_id)
        .order_by(ContractDeliverable.due_date.asc(), ContractDeliverable.id.asc())
        .all()
    )
    deliverables = [d.to_dict() for d in deliv_rows]
    deliverable_progress = compute_deliverable_progress(deliv_rows)

    versions = [
        {
            "version": v.version,
            "title": doc.title,
            "sha256": v.ciphertext_sha256,
            "created_at": v.created_at.strftime("%Y-%m-%d %H:%M UTC") if v.created_at else "",
        }
        for v in TSDocumentVersion.query.filter_by(tsd_id=doc.id)
        .order_by(TSDocumentVersion.version.desc())
        .limit(30)
        .all()
    ]

    comment_rows = (
        TSDComment.query.filter_by(tsd_id=doc.id)
        .order_by(TSDComment.created_at.desc())
        .limit(80)
        .all()
    )
    approval_rows = (
        TSDApproval.query.filter_by(tsd_id=doc.id, organization_id=org_id)
        .order_by(TSDApproval.id.desc())
        .limit(30)
        .all()
    )
    user_ids = {c.author_id for c in comment_rows if c.author_id} | {
        a.approver_id for a in approval_rows if a.approver_id
    }
    user_map = {}
    if user_ids:
        for u in User.query.filter(User.id.in_(list(user_ids))).all():
            user_map[u.id] = actor_label(u)

    comments = [
        {
            "id": c.id,
            "author": user_map.get(c.author_id, f"User #{c.author_id}"),
            "body": c.body,
            "anchor_quote": getattr(c, "anchor_text", "") or "",
            "resolved": bool(c.resolved_at),
            "created_at": c.created_at.strftime("%Y-%m-%d %H:%M UTC") if c.created_at else "",
        }
        for c in comment_rows
    ]

    approvals = [
        {
            "id": a.id,
            "approver_user_id": a.approver_id,
            "approver_name": user_map.get(a.approver_id, f"User #{a.approver_id}"),
            "decision": a.status,
            "comment": a.note or "",
            "decided_at": a.decided_at.strftime("%Y-%m-%d %H:%M UTC") if a.decided_at else "",
            "can_decide": a.approver_id == actor.id and a.status == "pending",
        }
        for a in approval_rows
    ]

    ext_shares = [
        {
            "id": s.id,
            "recipient_email": s.recipient_email,
            "permission": s.permission,
            "expires_at": s.expires_at.strftime("%Y-%m-%d %H:%M UTC") if s.expires_at else "",
            "revoked": bool(s.revoked_at),
        }
        for s in TSDExternalShare.query.filter_by(tsd_id=doc.id, organization_id=org_id)
        .filter(TSDExternalShare.revoked_at.is_(None))
        .order_by(TSDExternalShare.id.desc())
        .limit(20)
        .all()
    ]

    clauses = []
    try:
        clauses = ensure_default_approved_clauses(org_id, actor)
    except Exception:
        clauses = []

    obligations = [
        o.to_dict()
        for o in ContractObligation.query.filter_by(contract_id=wf.id, organization_id=org_id)
        .order_by(ContractObligation.due_date.asc(), ContractObligation.id.desc())
        .all()
    ]

    children = []
    for child_wf in ContractWorkflow.query.filter_by(
        parent_contract_id=wf.id, organization_id=org_id
    ).order_by(ContractWorkflow.id.desc()).all():
        cdoc = db.session.get(TSDocument, child_wf.document_id)
        if cdoc and not cdoc.deleted_at:
            children.append({
                "document_id": cdoc.id,
                "title": cdoc.title,
                "contract_number": child_wf.contract_number or f"CTR-{cdoc.id:04d}",
                "relationship_type": child_wf.relationship_type or "amendment",
                "contract_status": child_wf.canonical_status(),
                "stage": child_wf.stage,
                "stage_label": child_wf.to_dict()["stage_label"],
                "url": f"/contracts/{cdoc.id}/workflow",
            })

    parent_ref = None
    if wf.parent_contract_id:
        pwf = db.session.get(ContractWorkflow, wf.parent_contract_id)
        if pwf and pwf.organization_id == org_id:
            pdoc = db.session.get(TSDocument, pwf.document_id)
            if pdoc:
                parent_ref = {
                    "document_id": pdoc.id,
                    "title": pdoc.title,
                    "contract_number": pwf.contract_number or f"CTR-{pdoc.id:04d}",
                    "url": f"/contracts/{pdoc.id}/workflow",
                }

    org_users = [
        {"id": u.id, "name": actor_label(u), "email": u.email or ""}
        for u in User.query.filter_by(organization_id=org_id, is_active=True)
        .order_by(User.id.asc())
        .limit(100)
        .all()
    ]

    # Organization letterheads + built-in presets for instant in-module selection
    letterheads = []
    active_letterhead = None
    letterhead_presets = []
    try:
        from app.models.tsd_letterhead import LETTERHEAD_PRESETS, TSDLetterhead

        lh_rows = (
            TSDLetterhead.query.filter_by(organization_id=org_id)
            .filter(TSDLetterhead.deleted_at.is_(None))
            .order_by(TSDLetterhead.is_default.desc(), TSDLetterhead.name.asc())
            .all()
        )
        for lh in lh_rows:
            d_lh = lh.to_dict()
            letterheads.append(d_lh)
            if wf.letterhead_id and lh.id == wf.letterhead_id:
                active_letterhead = d_lh
        letterhead_presets = [
            {
                "slug": p["slug"],
                "label": p["label"],
                "category": p.get("category", "Executive"),
                "doc_type": p.get("doc_type", ""),
                "description": p.get("description", ""),
                "accent_color": (p.get("layout") or {}).get("accent_color", "#002769"),
                "brand_secondary": (p.get("layout") or {}).get("brand_secondary", "#02982e"),
                "paper_bg": (p.get("layout") or {}).get("paper_bg", "#ffffff"),
            }
            for p in LETTERHEAD_PRESETS
        ]
    except Exception:
        pass

    # Organization corporate stamps (auto-seed 3 official seals if org has none yet)
    stamps_out = []
    try:
        from app.models.tsd_stamp import TSDStamp

        st_rows = (
            TSDStamp.query.filter_by(organization_id=org_id)
            .filter(TSDStamp.deleted_at.is_(None))
            .order_by(TSDStamp.id.desc())
            .limit(40)
            .all()
        )
        if not st_rows and actor.id:
            _seed_stamps = [
                (
                    "Official Corporate Seal",
                    "seal",
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 180" width="140" height="140">'
                    '<circle cx="90" cy="90" r="82" fill="none" stroke="#002769" stroke-width="4"/>'
                    '<circle cx="90" cy="90" r="73" fill="none" stroke="#002769" stroke-width="1.5" stroke-dasharray="4 3"/>'
                    '<circle cx="90" cy="90" r="52" fill="none" stroke="#002769" stroke-width="1.5"/>'
                    '<text x="90" y="83" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" font-size="13" font-weight="700" fill="#002769">TRUSTSEAL</text>'
                    '<text x="90" y="100" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" font-size="9" font-weight="600" fill="#02982e">OFFICIAL SEAL</text>'
                    '<text x="90" y="128" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" font-size="8" fill="#002769">AUTHORIZED EXECUTION</text></svg>',
                ),
                (
                    "Approved & Executed Date Stamp",
                    "date",
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 96" width="170" height="74">'
                    '<rect x="4" y="4" width="212" height="88" fill="none" stroke="#02982e" stroke-width="3.5"/>'
                    '<rect x="10" y="10" width="200" height="76" fill="none" stroke="#02982e" stroke-width="1"/>'
                    '<text x="110" y="38" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" font-size="16" font-weight="800" letter-spacing="2" fill="#02982e">APPROVED</text>'
                    '<line x1="24" y1="48" x2="196" y2="48" stroke="#02982e" stroke-width="1.2"/>'
                    '<text x="110" y="68" text-anchor="middle" font-family="Courier,monospace" font-size="11" font-weight="700" fill="#002769">EXECUTED · TRUSTSEAL</text></svg>',
                ),
                (
                    "Certified True Copy Stamp",
                    "rubber",
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 84" width="170" height="65">'
                    '<rect x="4" y="4" width="212" height="76" fill="none" stroke="#8b1e24" stroke-width="3"/>'
                    '<text x="110" y="36" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" font-size="13" font-weight="800" letter-spacing="1.5" fill="#8b1e24">CERTIFIED TRUE COPY</text>'
                    '<text x="110" y="58" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" font-size="9.5" font-weight="600" fill="#8b1e24">VERIFIED ORIGINAL RECORD</text></svg>',
                ),
            ]
            for s_name, s_kind, s_svg in _seed_stamps:
                st_obj = TSDStamp(
                    organization_id=org_id,
                    created_by_id=actor.id,
                    name=s_name,
                    kind=s_kind,
                    layout={"label": s_name},
                    svg=s_svg,
                    status="published",
                )
                db.session.add(st_obj)
            db.session.commit()
            st_rows = (
                TSDStamp.query.filter_by(organization_id=org_id)
                .filter(TSDStamp.deleted_at.is_(None))
                .order_by(TSDStamp.id.desc())
                .limit(40)
                .all()
            )
        for s in st_rows:
            stamps_out.append({
                "id": s.id,
                "name": s.name,
                "kind": s.kind,
                "status": s.status or "published",
                "svg": s.svg or "",
            })
    except Exception:
        pass

    # Published Contract Templates + 1,050+ Library Catalog metadata
    templates = [
        t.to_dict()
        for t in ensure_default_templates(org_id, actor)
        if t.state == "published"
    ]
    from app.models.contract_templates_catalog import (
        get_catalog_categories_summary,
        get_contract_template_catalog,
    )
    catalog_total = len(get_contract_template_catalog())
    catalog_categories = get_catalog_categories_summary()

    return jsonify({
        "ok": True,
        "doc": {
            "id": doc.id,
            "title": doc.title,
            "status": doc.status,
            "version": doc.version,
            "ciphertext_sha256": doc.ciphertext_sha256,
            "updated_at": doc.updated_at.strftime("%Y-%m-%d %H:%M UTC") if doc.updated_at else "",
            "html": html_body,
        },
        "project": project.to_dict() if project else None,
        "projects": all_projects,
        "workflow": wf.to_dict(),
        "letterheads": letterheads,
        "active_letterhead": active_letterhead,
        "letterhead_presets": letterhead_presets,
        "stamps": stamps_out,
        "templates": templates,
        "catalog_total": catalog_total,
        "catalog_categories": catalog_categories,
        "key_terms": key_terms,
        "probation_term": probation_term,
        "deliverables": deliverables,
        "deliverable_progress": deliverable_progress,
        "versions": versions,
        "comments": comments,
        "approvals": approvals,
        "external_shares": ext_shares,
        "clauses": clauses,
        "obligations": obligations,
        "children": children,
        "parent": parent_ref,
        "org_users": org_users,
    })


@contracts_api.route("/<int:doc_id>/letterhead", methods=["POST"])
@login_required
def set_contract_letterhead(doc_id: int):
    doc, wf, actor = _owned_doc(doc_id)
    data = request.get_json(silent=True) or {}
    ok, err, lh = apply_letterhead_to_contract(
        doc=doc,
        wf=wf,
        actor=actor,
        letterhead_id=data.get("letterhead_id"),
        preset_slug=data.get("preset_slug"),
        custom_name=str(data.get("name") or ""),
    )
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True, "letterhead": lh, "workflow": wf.to_dict()})


@contracts_api.route("/<int:doc_id>/stamp", methods=["POST"])
@login_required
def attach_contract_stamp(doc_id: int):
    """Attach a corporate TSDStamp to the contract (enables seal & forensic verification)."""
    from app.models.tsd_stamp import TSDStamp

    doc, wf, actor = _owned_doc(doc_id)
    data = request.get_json(silent=True) or {}
    stamp_id = data.get("stamp_id")
    if not stamp_id:
        wf.stamp_id = None
        append_workflow_event(wf, actor, "Removed corporate stamp", "")
        db.session.commit()
        return jsonify({"ok": True, "stamp": None, "workflow": wf.to_dict()})

    stamp = (
        TSDStamp.query.filter_by(id=int(stamp_id), organization_id=actor.organization_id)
        .filter(TSDStamp.deleted_at.is_(None))
        .first()
    )
    if stamp is None:
        return jsonify({"error": "Selected stamp was not found"}), 404
    wf.stamp_id = stamp.id
    append_workflow_event(wf, actor, "Applied corporate stamp", f"{stamp.name} ({stamp.kind})")
    emit_contract_security_event(
        organization_id=actor.organization_id,
        actor_id=actor.id,
        action="contract.stamp_attached",
        document_id=doc.id,
    )
    db.session.commit()
    return jsonify({
        "ok": True,
        "stamp": {"id": stamp.id, "name": stamp.name, "kind": stamp.kind, "svg": stamp.svg or ""},
        "workflow": wf.to_dict(),
    })


@contracts_api.route("/<int:doc_id>/apply-template", methods=["POST"])
@login_required
def apply_contract_template_inplace(doc_id: int):
    doc, wf, actor = _owned_doc(doc_id)
    data = request.get_json(silent=True) or {}
    catalog_slug = str(data.get("catalog_slug") or "").strip()
    tpl_id = data.get("template_id")
    if catalog_slug:
        tpl = _materialize_catalog_template(catalog_slug, actor.organization_id, actor)
        if tpl is None:
            return jsonify({"error": "Catalog template not found"}), 404
    elif tpl_id:
        tpl = ContractTemplate.query.filter_by(
            id=int(tpl_id), organization_id=actor.organization_id
        ).first()
        if tpl is None:
            return jsonify({"error": "Contract template not found"}), 404
    else:
        return jsonify({"error": "template_id or catalog_slug is required"}), 400
    ok, err, summary = apply_template_to_contract(
        doc=doc,
        wf=wf,
        template=tpl,
        actor=actor,
        mode=str(data.get("mode") or "replace"),
        variables=data.get("variables") if isinstance(data.get("variables"), dict) else None,
        seed_key_terms=bool(data.get("seed_key_terms", True)),
        seed_deliverables=bool(data.get("seed_deliverables", True)),
    )
    if not ok:
        return jsonify({"error": err}), 409
    return jsonify({"ok": True, **summary, "workflow": wf.to_dict()})


@contracts_api.route("/<int:doc_id>/content", methods=["POST"])
@login_required
def update_contract_content(doc_id: int):
    doc, wf, actor = _owned_doc(doc_id)
    data = request.get_json(silent=True) or {}
    ok, err = save_contract_html(doc, wf, actor, data.get("html") or "")
    if not ok:
        return jsonify({"error": err}), 409
    return jsonify({
        "ok": True,
        "version": doc.version,
        "ciphertext_sha256": doc.ciphertext_sha256,
        "workflow": wf.to_dict(),
    })


@contracts_api.route("/<int:doc_id>/diff", methods=["GET"])
@login_required
def get_contract_diff(doc_id: int):
    doc, _wf, _actor = _owned_doc(doc_id)
    from_v = request.args.get("from", type=int) or max(1, (doc.version or 1) - 1)
    to_v = request.args.get("to", type=int)
    return jsonify({"ok": True, "diff": compute_version_diff(doc, from_v, to_v)})


@contracts_api.route("/<int:doc_id>/stage", methods=["POST"])
@login_required
def post_contract_stage(doc_id: int):
    doc, wf, actor = _owned_doc(doc_id)
    data = request.get_json(silent=True) or {}
    stage = (data.get("stage") or "").strip().lower()
    note = (data.get("note") or "").strip()[:400]
    ok, err = transition_stage(doc=doc, wf=wf, actor=actor, target_stage=stage, note=note)
    if not ok:
        return jsonify({"error": err}), 400
    db.session.commit()
    return jsonify({"ok": True, "stage": wf.stage, "contract_status": wf.contract_status, "status": doc.status, "workflow": wf.to_dict()})


@contracts_api.route("/<int:doc_id>/suspend", methods=["POST"])
@login_required
def post_contract_suspend(doc_id: int):
    doc, wf, actor = _owned_doc(doc_id)
    data = request.get_json(silent=True) or {}
    ok, err = suspend_contract(
        doc=doc,
        wf=wf,
        actor=actor,
        reason=str(data.get("reason") or ""),
        expected_resume_date=str(data.get("expected_resume_date") or ""),
    )
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True, "workflow": wf.to_dict()})


@contracts_api.route("/<int:doc_id>/resume", methods=["POST"])
@login_required
def post_contract_resume(doc_id: int):
    doc, wf, actor = _owned_doc(doc_id)
    data = request.get_json(silent=True) or {}
    ok, err = resume_contract(
        doc=doc,
        wf=wf,
        actor=actor,
        note=str(data.get("note") or ""),
        shift_due_dates_days=int(data.get("shift_due_dates_days") or 0),
    )
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True, "workflow": wf.to_dict()})


@contracts_api.route("/<int:doc_id>/meta", methods=["POST"])
@login_required
def post_contract_meta(doc_id: int):
    doc, wf, actor = _owned_doc(doc_id)
    data = request.get_json(silent=True) or {}
    if "project_id" in data and data.get("project_id"):
        proj = Project.query.filter_by(
            id=int(data["project_id"]), organization_id=doc.organization_id
        ).first()
        if proj is None:
            return jsonify({"error": "Project not found"}), 404
        wf.project_id = proj.id
    for field, attr, limit in (
        ("contract_number", "contract_number", 64),
        ("contract_type", "contract_type", 48),
        ("counterparty_name", "counterparty_name", 200),
        ("deal_value", "deal_value", 64),
        ("currency", "currency", 12),
        ("effective_date", "effective_date", 32),
        ("expiration_date", "expiration_date", 32),
        ("governing_law", "governing_law", 120),
        ("renewal_type", "renewal_type", 24),
        ("routing_mode", "routing_mode", 24),
    ):
        if field in data:
            setattr(wf, attr, str(data.get(field) or "").strip()[:limit])
    if "notice_period_days" in data and data.get("notice_period_days") not in (None, ""):
        try:
            wf.notice_period_days = max(0, min(365, int(data["notice_period_days"])))
        except (TypeError, ValueError):
            pass
    if "renewal_term_months" in data:
        val = data.get("renewal_term_months")
        wf.renewal_term_months = int(val) if val not in (None, "") else None
    if "stamp_id" in data:
        wf.stamp_id = int(data["stamp_id"]) if data.get("stamp_id") else None
    if "letterhead_id" in data:
        wf.letterhead_id = int(data["letterhead_id"]) if data.get("letterhead_id") else None
    if isinstance(data.get("checklist"), dict):
        chk = dict(wf.checklist_json or {})
        for k, v in data["checklist"].items():
            chk[str(k)] = bool(v)
        wf.checklist_json = chk
        flag_modified(wf, "checklist_json")

    emit_contract_security_event(
        organization_id=doc.organization_id,
        actor_id=actor.id,
        action="contract.meta_update",
        document_id=doc.id,
    )
    db.session.commit()
    return jsonify({"ok": True, "workflow": wf.to_dict()})


# ---- Key Terms & Probation Endpoints ----

@contracts_api.route("/<int:doc_id>/key-terms", methods=["POST"])
@login_required
def create_key_term(doc_id: int):
    doc, wf, actor = _owned_doc(doc_id)
    data = request.get_json(silent=True) or {}
    label = str(data.get("label") or "").strip()[:200]
    if not label:
        return jsonify({"error": "Key term label is required"}), 400
    num_val = None
    if data.get("numeric_value") not in (None, ""):
        try:
            num_val = float(data["numeric_value"])
        except (TypeError, ValueError):
            pass
    kt = ContractKeyTerm(
        organization_id=doc.organization_id,
        contract_id=wf.id,
        category=str(data.get("category") or "custom").strip()[:32],
        term_key=str(data.get("term_key") or "").strip()[:64] or None,
        label=label,
        value_text=str(data.get("value_text") or "").strip()[:300],
        numeric_value=num_val,
        unit=str(data.get("unit") or "").strip()[:32] or None,
        start_date=str(data.get("start_date") or "").strip()[:32] or None,
        end_date=str(data.get("end_date") or "").strip()[:32] or None,
        alert_days_before=max(0, min(180, int(data.get("alert_days_before") or 14))),
        status=str(data.get("status") or "active").strip()[:24],
        clause_ref=str(data.get("clause_ref") or "").strip()[:120] or None,
        notes=str(data.get("notes") or "").strip()[:500] or None,
    )
    db.session.add(kt)
    append_workflow_event(wf, actor, "Key term added", f"{label} ({kt.category})")
    emit_contract_security_event(
        organization_id=doc.organization_id,
        actor_id=actor.id,
        action="contract.key_term_added",
        document_id=doc.id,
    )
    db.session.commit()
    return jsonify({"ok": True, "key_term": kt.to_dict()}), 201


@contracts_api.route("/<int:doc_id>/key-terms/<int:kt_id>", methods=["PATCH", "DELETE"])
@login_required
def mutate_key_term(doc_id: int, kt_id: int):
    doc, wf, actor = _owned_doc(doc_id)
    kt = ContractKeyTerm.query.filter_by(
        id=kt_id, contract_id=wf.id, organization_id=doc.organization_id
    ).first()
    if kt is None:
        abort(404)
    if request.method == "DELETE":
        db.session.delete(kt)
        db.session.commit()
        return jsonify({"ok": True})
    data = request.get_json(silent=True) or {}
    if "status" in data and data["status"] in ("active", "met", "at_risk", "breached", "waived", "expired"):
        kt.status = data["status"]
    if "value_text" in data:
        kt.value_text = str(data.get("value_text") or "").strip()[:300]
    if "end_date" in data:
        kt.end_date = str(data.get("end_date") or "").strip()[:32] or None
    if "notes" in data:
        kt.notes = str(data.get("notes") or "").strip()[:500] or None
    append_workflow_event(wf, actor, f"Key term updated ({kt.status})", kt.label)
    db.session.commit()
    return jsonify({"ok": True, "key_term": kt.to_dict()})


@contracts_api.route("/<int:doc_id>/probation/action", methods=["POST"])
@login_required
def probation_action(doc_id: int):
    """First-class probation actions: confirm, extend, or terminate_on_probation."""
    doc, wf, actor = _owned_doc(doc_id)
    data = request.get_json(silent=True) or {}
    action = str(data.get("action") or "").strip().lower()
    note = str(data.get("note") or "").strip()[:400]

    pt = ContractKeyTerm.query.filter_by(
        contract_id=wf.id, organization_id=doc.organization_id, category="probation"
    ).first()
    if pt is None:
        return jsonify({"error": "No probation key term is configured on this contract."}), 404

    if action == "confirm":
        pt.status = "met"
        pt.notes = note or "Probation successfully completed and confirmed."
        append_workflow_event(wf, actor, "Probation Confirmed", pt.notes)
        emit_contract_security_event(
            organization_id=doc.organization_id,
            actor_id=actor.id,
            action="contract.probation_confirmed",
            document_id=doc.id,
        )
        db.session.commit()
        return jsonify({"ok": True, "key_term": pt.to_dict(), "workflow": wf.to_dict()})

    if action == "extend":
        extra_days = max(7, min(365, int(data.get("extend_days") or 30)))
        try:
            base = datetime.strptime(pt.end_date[:10], "%Y-%m-%d") if pt.end_date else datetime.utcnow()
        except ValueError:
            base = datetime.utcnow()
        new_end = (base + timedelta(days=extra_days)).strftime("%Y-%m-%d")
        pt.end_date = new_end
        pt.status = "active"
        pt.notes = f"Extended by {extra_days} days to {new_end}" + (f" · {note}" if note else "")
        append_workflow_event(wf, actor, f"Probation Extended (+{extra_days}d)", pt.notes)
        emit_contract_security_event(
            organization_id=doc.organization_id,
            actor_id=actor.id,
            action="contract.probation_extended",
            document_id=doc.id,
        )
        db.session.commit()
        return jsonify({"ok": True, "key_term": pt.to_dict(), "workflow": wf.to_dict()})

    if action == "terminate":
        pt.status = "breached"
        pt.notes = note or "Terminated during probation period."
        ok, err = terminate_contract_record(
            doc=doc,
            wf=wf,
            actor=actor,
            reason=pt.notes,
            termination_type="probation_failed",
        )
        if not ok:
            return jsonify({"error": err}), 400
        return jsonify({"ok": True, "key_term": pt.to_dict(), "workflow": wf.to_dict()})

    return jsonify({"error": "Invalid probation action (expected confirm, extend, or terminate)"}), 400


# ---- Project Deliverables & Milestone Acceptance Endpoints ----

@contracts_api.route("/<int:doc_id>/deliverables", methods=["POST"])
@login_required
def create_deliverable(doc_id: int):
    doc, wf, actor = _owned_doc(doc_id)
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()[:200]
    if not title:
        return jsonify({"error": "Deliverable title is required"}), 400
    pay = None
    if data.get("payment_amount") not in (None, ""):
        try:
            pay = float(data["payment_amount"])
        except (TypeError, ValueError):
            pass
    init_status = "suspended" if wf.canonical_status() == "SUSPENDED" else (
        "in_progress" if wf.canonical_status() == "SIGNED" else "not_started"
    )
    dl = ContractDeliverable(
        organization_id=doc.organization_id,
        contract_id=wf.id,
        title=title,
        description=str(data.get("description") or "").strip()[:500] or None,
        deliverable_type=str(data.get("deliverable_type") or "milestone").strip()[:32],
        project_phase=str(data.get("project_phase") or "").strip()[:80] or None,
        owner_name=str(data.get("owner_name") or actor_label(actor)).strip()[:140],
        counterparty_owner=str(data.get("counterparty_owner") or wf.counterparty_name or "").strip()[:140] or None,
        due_date=str(data.get("due_date") or "").strip()[:32] or None,
        weight_pct=max(1, min(100, int(data.get("weight_pct") or 10))),
        payment_amount=pay,
        acceptance_criteria=str(data.get("acceptance_criteria") or "").strip()[:500] or None,
        status=init_status,
    )
    db.session.add(dl)
    append_workflow_event(wf, actor, "Deliverable added", f"{title}" + (f" (due {dl.due_date})" if dl.due_date else ""))
    emit_contract_security_event(
        organization_id=doc.organization_id,
        actor_id=actor.id,
        action="contract.deliverable_added",
        document_id=doc.id,
    )
    db.session.commit()
    return jsonify({"ok": True, "deliverable": dl.to_dict()}), 201


@contracts_api.route("/<int:doc_id>/deliverables/<int:dl_id>", methods=["PATCH", "DELETE"])
@login_required
def mutate_deliverable(doc_id: int, dl_id: int):
    doc, wf, actor = _owned_doc(doc_id)
    dl = ContractDeliverable.query.filter_by(
        id=dl_id, contract_id=wf.id, organization_id=doc.organization_id
    ).first()
    if dl is None:
        abort(404)
    if request.method == "DELETE":
        db.session.delete(dl)
        db.session.commit()
        return jsonify({"ok": True})
    data = request.get_json(silent=True) or {}
    if "status" in data and data["status"] in (
        "not_started", "in_progress", "submitted", "accepted", "rejected", "overdue", "suspended", "cancelled"
    ):
        dl.status = data["status"]
        if dl.status == "accepted":
            dl.accepted_at = datetime.utcnow()
            dl.accepted_by_id = actor.id
    if "evidence_note" in data:
        dl.evidence_note = str(data.get("evidence_note") or "").strip()[:500] or None
    append_workflow_event(wf, actor, f"Deliverable {dl.status}", dl.title)
    emit_contract_security_event(
        organization_id=doc.organization_id,
        actor_id=actor.id,
        action=f"contract.deliverable_{dl.status}",
        document_id=doc.id,
    )
    db.session.commit()
    return jsonify({"ok": True, "deliverable": dl.to_dict()})


# ---- Signers, Closing, PDF, Binder, Obligations, Amendments, Termination ----

@contracts_api.route("/<int:doc_id>/signers", methods=["POST"])
@login_required
def post_contract_signers(doc_id: int):
    doc, wf, actor = _owned_doc(doc_id)
    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "add").lower()
    signers = list(wf.signers_json or [])

    if action == "add":
        name = str(data.get("name") or "").strip()[:140]
        email = str(data.get("email") or "").strip()[:180]
        role = str(data.get("role") or "Counterparty Signatory").strip()[:120]
        if not name:
            return jsonify({"error": "Signatory name is required"}), 400
        sid = f"sig-{int(datetime.utcnow().timestamp() * 1000)}"
        signers.append({
            "id": sid,
            "order": len(signers) + 1,
            "name": name,
            "email": email,
            "role": role,
            "status": "pending",
            "signed_at": "",
            "signature_text": "",
            "signature_svg": "",
        })
        append_workflow_event(wf, actor, "Signatory added", f"{name} ({role})")
    elif action == "remove":
        sid = str(data.get("id") or "")
        signers = [s for s in signers if s.get("id") != sid]
        for idx, s in enumerate(signers, start=1):
            s["order"] = idx
        append_workflow_event(wf, actor, "Signatory removed", sid)

    wf.signers_json = signers
    flag_modified(wf, "signers_json")
    emit_contract_security_event(
        organization_id=doc.organization_id,
        actor_id=actor.id,
        action="contract.signers_updated",
        document_id=doc.id,
    )
    db.session.commit()
    return jsonify({"ok": True, "workflow": wf.to_dict()})


@contracts_api.route("/<int:doc_id>/sign", methods=["POST"])
@login_required
def post_contract_sign(doc_id: int):
    doc, wf, actor = _owned_doc(doc_id)
    data = request.get_json(silent=True) or {}
    sid = str(data.get("id") or "")
    sig_text = str(data.get("signature_text") or "").strip()[:140]
    signers = list(wf.signers_json or [])

    if (wf.routing_mode or "parallel") == "sequential":
        for s in signers:
            if s.get("id") == sid:
                break
            if s.get("status") != "signed":
                return jsonify({
                    "error": f"Sequential signing enabled: waiting for {s.get('name')} to sign first."
                }), 409

    matched = None
    for s in signers:
        if s.get("id") == sid:
            s["status"] = "signed"
            s["signed_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
            s["signature_text"] = sig_text or s.get("name") or actor_label(actor)
            matched = s
            break
    if not matched:
        return jsonify({"error": "signer_not_found"}), 404

    wf.signers_json = signers
    flag_modified(wf, "signers_json")
    if wf.stage in ("draft", "review", "negotiation", "approval"):
        wf.stage = "signature"
        wf.edit_locked = True
    append_workflow_event(
        wf, actor, "Agreement signed with TrustSeal", f"{matched['name']} · {matched['role']}"
    )
    emit_contract_security_event(
        organization_id=doc.organization_id,
        actor_id=actor.id,
        action="contract.signed",
        document_id=doc.id,
    )
    db.session.commit()
    return jsonify({"ok": True, "workflow": wf.to_dict()})


@contracts_api.route("/<int:doc_id>/close", methods=["POST"])
@login_required
def post_contract_close(doc_id: int):
    doc, wf, actor = _owned_doc(doc_id)
    data = request.get_json(silent=True) or {}
    stamp_id = data.get("stamp_id")
    note = str(data.get("note") or "").strip()[:300]
    result = close_and_seal_contract(
        doc=doc, wf=wf, actor=actor, stamp_id=stamp_id, closing_note=note
    )
    return jsonify({"ok": True, **result})


@contracts_api.route("/<int:doc_id>/pdf", methods=["GET"])
@login_required
def stream_contract_pdf(doc_id: int):
    doc, wf, _actor = _owned_doc(doc_id)
    pdf_bytes = render_contract_pdf(doc, wf)
    disp = "attachment" if request.args.get("download") == "1" else "inline"
    safe_num = (wf.contract_number or f"contract-{doc.id}").replace(" ", "_")
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'{disp}; filename="{safe_num}.pdf"',
            "Cache-Control": "no-store",
        },
    )


@contracts_api.route("/<int:doc_id>/binder", methods=["GET"])
@login_required
def download_closing_binder(doc_id: int):
    doc, wf, _actor = _owned_doc(doc_id)
    pdf_bytes = render_contract_pdf(doc, wf)
    tsd_bytes = serialize_container(
        organization_id=doc.organization_id,
        document_id=doc.id,
        document_version=doc.version,
        title=doc.title,
        created_by_id=doc.created_by_id,
        created_at=doc.created_at or datetime.utcnow(),
        ciphertext=doc.ciphertext,
        export_policy=doc.export_policy,
    )
    manifest = {
        "schema": "trustseal.contract-closing-binder.v2",
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "contract_number": wf.contract_number,
        "contract_status": wf.canonical_status(),
        "project_id": wf.project_id,
        "title": doc.title,
        "stage": wf.stage,
        "counterparty": wf.counterparty_name,
        "deal_value": f"{wf.currency} {wf.deal_value}" if wf.deal_value else "",
        "closed_at": wf.closed_at.isoformat() + "Z" if wf.closed_at else None,
        "execution_sha256": wf.execution_sha256,
        "vault_sha256": doc.ciphertext_sha256,
        "evidence_retention_id": wf.evidence_retention_id,
        "stamp_receipt_id": wf.stamp_receipt_id,
        "signers": wf.signers_json or [],
        "events": wf.events_json or [],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("executed_contract.pdf", pdf_bytes)
        zf.writestr("contract_vault.tsd", tsd_bytes)
        zf.writestr("evidence_manifest.json", json.dumps(manifest, indent=2))
    buf.seek(0)
    safe_num = (wf.contract_number or f"contract-{doc.id}").replace(" ", "_")
    return Response(
        buf.getvalue(),
        mimetype="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_num}-closing-binder.zip"',
            "Cache-Control": "no-store",
        },
    )


@contracts_api.route("/<int:doc_id>/obligations", methods=["POST"])
@login_required
def create_obligation(doc_id: int):
    doc, wf, actor = _owned_doc(doc_id)
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()[:200]
    if not title:
        return jsonify({"error": "Obligation title is required"}), 400
    ob = ContractObligation(
        organization_id=doc.organization_id,
        contract_id=wf.id,
        title=title,
        category=str(data.get("category") or "deliverable").strip()[:32],
        owner_name=str(data.get("owner_name") or actor_label(actor)).strip()[:140],
        due_date=str(data.get("due_date") or "").strip()[:32] or None,
        status="pending",
        notes=str(data.get("notes") or "").strip()[:500] or None,
    )
    db.session.add(ob)
    append_workflow_event(wf, actor, "Obligation added", f"{title}" + (f" (due {ob.due_date})" if ob.due_date else ""))
    emit_contract_security_event(
        organization_id=doc.organization_id,
        actor_id=actor.id,
        action="contract.obligation_added",
        document_id=doc.id,
    )
    db.session.commit()
    return jsonify({"ok": True, "obligation": ob.to_dict()})


@contracts_api.route("/<int:doc_id>/obligations/<int:ob_id>", methods=["PATCH", "DELETE"])
@login_required
def mutate_obligation(doc_id: int, ob_id: int):
    doc, wf, actor = _owned_doc(doc_id)
    ob = ContractObligation.query.filter_by(
        id=ob_id, contract_id=wf.id, organization_id=doc.organization_id
    ).first()
    if ob is None:
        abort(404)
    if request.method == "DELETE":
        db.session.delete(ob)
        db.session.commit()
        return jsonify({"ok": True})
    data = request.get_json(silent=True) or {}
    if "status" in data:
        st = str(data["status"]).strip().lower()
        if st in ("pending", "in_progress", "completed"):
            ob.status = st
            ob.completed_at = datetime.utcnow() if st == "completed" else None
    if "notes" in data:
        ob.notes = str(data["notes"] or "").strip()[:500] or None
    append_workflow_event(wf, actor, f"Obligation {ob.status}", ob.title)
    db.session.commit()
    return jsonify({"ok": True, "obligation": ob.to_dict()})


@contracts_api.route("/<int:doc_id>/amendment", methods=["POST"])
@login_required
def spawn_amendment(doc_id: int):
    doc, wf, actor = _owned_doc(doc_id)
    data = request.get_json(silent=True) or {}
    rel = str(data.get("relationship_type") or "amendment").strip().lower()
    title = str(data.get("title") or "").strip()
    new_doc, new_wf = create_linked_contract(
        parent_doc=doc, parent_wf=wf, actor=actor, relationship_type=rel, title=title
    )
    return jsonify({
        "ok": True,
        "document_id": new_doc.id,
        "contract_number": new_wf.contract_number,
        "url": f"/contracts/{new_doc.id}/workflow",
    })


@contracts_api.route("/<int:doc_id>/terminate", methods=["POST"])
@login_required
def terminate_contract(doc_id: int):
    doc, wf, actor = _owned_doc(doc_id)
    data = request.get_json(silent=True) or {}
    ok, err = terminate_contract_record(
        doc=doc,
        wf=wf,
        actor=actor,
        reason=str(data.get("reason") or ""),
        termination_type=str(data.get("termination_type") or "mutual"),
    )
    if not ok:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True, "workflow": wf.to_dict()})


@contracts_api.route("/<int:doc_id>/external-review", methods=["POST"])
@login_required
def issue_external_review_link(doc_id: int):
    doc, wf, actor = _owned_doc(doc_id)
    data = request.get_json(silent=True) or {}
    email = str(data.get("email") or "").strip()[:180]
    permission = str(data.get("permission") or "comment").strip().lower()
    if permission not in ("view", "comment"):
        permission = "comment"
    days = max(1, min(30, int(data.get("expires_days") or 7)))
    if not email or "@" not in email:
        return jsonify({"error": "Valid counterparty email is required"}), 400

    raw_token = new_token()
    share = TSDExternalShare(
        tsd_id=doc.id,
        organization_id=doc.organization_id,
        created_by_id=actor.id,
        recipient_email=email,
        permission=permission,
        token_hash=hash_token(raw_token),
        expires_at=datetime.utcnow() + timedelta(days=days),
    )
    db.session.add(share)
    if wf.stage in ("draft", "review"):
        wf.stage = "negotiation"
    append_workflow_event(wf, actor, "Shared with counterparty for negotiation", f"{email} ({permission}, {days}d)")
    emit_contract_security_event(
        organization_id=doc.organization_id,
        actor_id=actor.id,
        action="contract.external_review_shared",
        document_id=doc.id,
    )
    db.session.commit()
    return jsonify({
        "ok": True,
        "share_url": f"{request.host_url.rstrip('/')}/documents/shared/{raw_token}",
        "workflow": wf.to_dict(),
    })
