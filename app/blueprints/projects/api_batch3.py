"""Batch 3 Enterprise Project Management REST APIs (PM-23, PM-25, PM-28, PM-29, PM-31, PM-32)."""
from __future__ import annotations

import csv
import hashlib
import io
from datetime import datetime, timedelta, timezone

from flask import Blueprint, Response, abort, jsonify, request
from flask_login import current_user, login_required

from app.extensions import db
from app.models.contract_workflow import ContractDeliverable, ContractWorkflow, Project
from app.models.project_enterprise_batch3 import (
    ProjectApprovalRequest,
    ProjectComment,
    ProjectComplianceRecord,
    ProjectExternalGrant,
    ProjectTemplate,
    generate_portal_token,
    hash_portal_token,
)
from app.models.project_management import (
    ProjectGate,
    ProjectMembership,
    ProjectTask,
    ProjectWBSNode,
    parse_iso_date,
    to_decimal,
)
from app.blueprints.projects.permissions import (
    assert_project_mutable,
    can_approve_project_governance,
    load_authorized_project,
)
from app.blueprints.projects.services import emit_project_event

projects_batch3_api = Blueprint("projects_batch3_api", __name__, url_prefix="/api/projects")
project_templates_api = Blueprint("project_templates_api", __name__, url_prefix="/api/project-templates")
project_portal_api = Blueprint("project_portal_api", __name__, url_prefix="/api/project-portal")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _actor():
    if not current_user.is_authenticated:
        abort(401)
    if current_user.organization_id is None:
        abort(403, description="organization_required")
    return current_user


def _csv_safe(val: object) -> str:
    """Neutralize spreadsheet formula injection (Spec Section 11 Security)."""
    s = str(val if val is not None else "")
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


# =====================================================================
# PM-23: COLLABORATION COMMENTS & MY WORK INBOX
# =====================================================================

@projects_batch3_api.route("/my-work", methods=["GET"])
@login_required
def my_work_inbox():
    actor = _actor()
    tasks = ProjectTask.query.filter_by(
        organization_id=actor.organization_id, assignee_user_id=actor.id
    ).filter(ProjectTask.status != "done").order_by(ProjectTask.id.desc()).all()
    pending_approvals = ProjectApprovalRequest.query.filter_by(
        organization_id=actor.organization_id, status="pending"
    ).filter(ProjectApprovalRequest.requested_by_id != actor.id).order_by(ProjectApprovalRequest.id.desc()).all()
    return jsonify({
        "ok": True,
        "my_tasks": [t.to_dict() for t in tasks],
        "pending_approvals": [a.to_dict() for a in pending_approvals],
    })


@projects_batch3_api.route("/<int:project_id>/comments", methods=["GET", "POST"])
@login_required
def project_comments_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))

    if request.method == "GET":
        rows = ProjectComment.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).order_by(ProjectComment.id.desc()).all()
        return jsonify({"ok": True, "comments": [r.to_dict() for r in rows]})

    data = request.get_json(silent=True) or {}
    body = str(data.get("body") or "").strip()
    if not body:
        return jsonify({"error": "Comment body is required"}), 422
    c = ProjectComment(
        organization_id=proj.organization_id,
        project_id=proj.id,
        parent_id=int(data["parent_id"]) if str(data.get("parent_id") or "").isdigit() else None,
        author_user_id=actor.id,
        author_name=getattr(actor, "full_name", None) or actor.username or actor.email,
        body=body[:4000],
    )
    db.session.add(c)
    db.session.commit()
    return jsonify({"ok": True, "comment": c.to_dict()}), 201


# =====================================================================
# PM-25: GOVERNED APPROVALS & SUBJECT HASH BINDING
# =====================================================================

@projects_batch3_api.route("/<int:project_id>/approvals", methods=["GET", "POST"])
@login_required
def project_approvals_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))

    if request.method == "GET":
        rows = ProjectApprovalRequest.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).order_by(ProjectApprovalRequest.id.desc()).all()
        return jsonify({"ok": True, "approvals": [r.to_dict() for r in rows]})

    assert_project_mutable(proj)
    data = request.get_json(silent=True) or {}
    title = str(data.get("subject_title") or "").strip()[:220]
    if not title:
        return jsonify({"error": "subject_title is required"}), 422
    raw_content = str(data.get("subject_payload") or title)
    subj_hash = str(data.get("subject_hash") or hashlib.sha256(raw_content.encode("utf-8")).hexdigest())[:64]

    req = ProjectApprovalRequest(
        organization_id=proj.organization_id,
        project_id=proj.id,
        subject_type=str(data.get("subject_type") or "deliverable").strip()[:32],
        subject_title=title,
        subject_hash=subj_hash,
        approval_mode=str(data.get("approval_mode") or "internal").strip()[:24],
        enforce_sod=bool(data.get("enforce_sod", True)),
        requested_by_id=actor.id,
        status="pending",
    )
    db.session.add(req)
    db.session.commit()
    return jsonify({"ok": True, "approval": req.to_dict()}), 201


@projects_batch3_api.route("/<int:project_id>/approvals/<int:aid>/decide", methods=["POST"])
@login_required
def decide_project_approval(project_id: int, aid: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    if not can_approve_project_governance(proj, actor):
        abort(403, description="governance_approval_required")
    req = ProjectApprovalRequest.query.filter_by(id=aid, project_id=proj.id, organization_id=proj.organization_id).first()
    if req is None:
        abort(404)
    if req.enforce_sod and req.requested_by_id == actor.id:
        return jsonify({"error": "Separation of duties: requester cannot self-approve"}), 403
    data = request.get_json(silent=True) or {}
    # Spec PM-25: stale subject cannot be approved under old hash
    if data.get("expected_hash") and str(data["expected_hash"]) != req.subject_hash:
        return jsonify({"error": "Stale subject hash: content changed since approval request"}), 409
    decision = str(data.get("decision") or "approved").strip().lower()
    if decision not in ("approved", "rejected"):
        return jsonify({"error": "decision must be approved or rejected"}), 422

    req.status = decision
    req.decision_note = str(data.get("decision_note") or "").strip() or None
    req.decided_by_id = actor.id
    req.decided_at = _utcnow()
    emit_project_event(
        organization_id=proj.organization_id,
        actor_id=actor.id,
        event_type=f"approval.{decision}",
        aggregate_type="project_approval_request",
        aggregate_id=req.id,
        payload={"project_id": proj.id, "subject_hash": req.subject_hash},
    )
    db.session.commit()
    return jsonify({"ok": True, "approval": req.to_dict()})


# =====================================================================
# PM-28: COMPLIANCE, PERMITS & RESTRICTED HSE INCIDENTS
# =====================================================================

@projects_batch3_api.route("/<int:project_id>/compliance", methods=["GET", "POST"])
@login_required
def project_compliance_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))
    can_see_restricted = can_approve_project_governance(proj, actor)

    if request.method == "GET":
        q = ProjectComplianceRecord.query.filter_by(organization_id=proj.organization_id, project_id=proj.id)
        if not can_see_restricted:
            q = q.filter(ProjectComplianceRecord.is_restricted.is_(False))
        rows = q.order_by(ProjectComplianceRecord.id.desc()).all()
        return jsonify({"ok": True, "compliance_records": [r.to_dict() for r in rows]})

    assert_project_mutable(proj)
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()[:220]
    if not title:
        return jsonify({"error": "Compliance title is required"}), 422
    rtype = str(data.get("record_type") or "permit").strip()[:24]
    rec = ProjectComplianceRecord(
        organization_id=proj.organization_id,
        project_id=proj.id,
        record_type=rtype,
        title=title,
        authority=str(data.get("authority") or "").strip()[:160] or None,
        is_mandatory=bool(data.get("is_mandatory", True)),
        is_restricted=bool(data.get("is_restricted", rtype == "hse_incident")),
        expiry_date=parse_iso_date(data.get("expiry_date")),
        status=str(data.get("status") or "active").strip()[:24],
        details=str(data.get("details") or "").strip() or None,
        reported_by_id=actor.id,
    )
    db.session.add(rec)
    db.session.commit()
    return jsonify({"ok": True, "compliance_record": rec.to_dict()}), 201


# =====================================================================
# PM-29: EXTERNAL CLIENT & PARTNER COLLABORATION PORTAL
# =====================================================================

@projects_batch3_api.route("/<int:project_id>/external-grants", methods=["GET", "POST"])
@login_required
def project_external_grants_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))

    if request.method == "GET":
        rows = ProjectExternalGrant.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).order_by(ProjectExternalGrant.id.desc()).all()
        return jsonify({"ok": True, "grants": [r.to_dict() for r in rows]})

    if not can_approve_project_governance(proj, actor):
        abort(403, description="external_sharing_permission_required")
    data = request.get_json(silent=True) or {}
    rname = str(data.get("recipient_name") or "").strip()[:160]
    remail = str(data.get("recipient_email") or "").strip()[:180]
    if not rname or not remail:
        return jsonify({"error": "recipient_name and recipient_email are required"}), 422
    ttl_days = max(1, min(90, int(data.get("expires_days") or 14)))
    raw_token, tok_hash = generate_portal_token()
    grant = ProjectExternalGrant(
        organization_id=proj.organization_id,
        project_id=proj.id,
        recipient_name=rname,
        recipient_email=remail,
        token_hash=tok_hash,
        scope_json=data.get("scope") or {"summary": True, "milestones": True},
        expires_at=_utcnow() + timedelta(days=ttl_days),
        granted_by_id=actor.id,
    )
    db.session.add(grant)
    db.session.commit()
    return jsonify({
        "ok": True,
        "grant": grant.to_dict(),
        "portal_token": raw_token,
        "portal_url": f"/api/project-portal/{raw_token}",
    }), 201


@projects_batch3_api.route("/<int:project_id>/external-grants/<int:gid>/revoke", methods=["POST"])
@login_required
def revoke_external_grant(project_id: int, gid: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    grant = ProjectExternalGrant.query.filter_by(id=gid, project_id=proj.id, organization_id=proj.organization_id).first()
    if grant is None:
        abort(404)
    grant.revoked_at = _utcnow()
    db.session.commit()
    return jsonify({"ok": True, "grant": grant.to_dict()})


@project_portal_api.route("/<raw_token>", methods=["GET"])
def external_portal_view(raw_token: str):
    """Scoped external client/partner view. Never exposes internal costs, budgets, or rates."""
    tok_hash = hash_portal_token(raw_token)
    grant = ProjectExternalGrant.query.filter_by(token_hash=tok_hash).first()
    if grant is None or not grant.is_valid():
        return jsonify({"error": "Portal link is invalid, expired, or revoked"}), 403
    proj = Project.query.filter_by(id=grant.project_id, organization_id=grant.organization_id).first()
    if proj is None:
        abort(404)
    wfs = ContractWorkflow.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).all()
    wf_ids = [w.id for w in wfs]
    milestones = []
    if wf_ids and (grant.scope_json or {}).get("milestones", True):
        delivs = ContractDeliverable.query.filter(
            ContractDeliverable.organization_id == proj.organization_id,
            ContractDeliverable.contract_id.in_(wf_ids),
        ).all()
        milestones = [{"title": d.title, "due_date": d.due_date or "", "status": d.status} for d in delivs]
    return jsonify({
        "ok": True,
        "recipient": grant.recipient_name,
        "project": {
            "project_code": proj.project_code,
            "name": proj.name,
            "lifecycle_state": proj.lifecycle_state,
            "status": proj.status,
        },
        "milestones": milestones,
    })


# =====================================================================
# PM-31: REUSABLE PROJECT TEMPLATES
# =====================================================================

@project_templates_api.route("", methods=["GET", "POST"])
@project_templates_api.route("/", methods=["GET", "POST"])
@login_required
def project_templates_collection():
    actor = _actor()
    org_id = actor.organization_id

    if request.method == "GET":
        rows = ProjectTemplate.query.filter_by(organization_id=org_id).order_by(ProjectTemplate.id.desc()).all()
        return jsonify({"ok": True, "templates": [r.to_dict() for r in rows]})

    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()[:200]
    if not name:
        return jsonify({"error": "Template name is required"}), 422
    cnt = ProjectTemplate.query.filter_by(organization_id=org_id).count()
    tpl = ProjectTemplate(
        organization_id=org_id,
        code=str(data.get("code") or f"PTPL-{cnt + 1:03d}").strip()[:40],
        name=name,
        category=str(data.get("category") or "client_delivery").strip()[:48],
        delivery_methodology=str(data.get("delivery_methodology") or "hybrid").strip()[:24],
        version=int(data.get("version") or 1),
        default_wbs_json=data.get("default_wbs") or [
            {"wbs_code": "1.0", "title": "Initiation & Mobilization", "weight_pct": 20},
            {"wbs_code": "2.0", "title": "Core Execution", "weight_pct": 60},
            {"wbs_code": "3.0", "title": "Handover & Closure", "weight_pct": 20},
        ],
        default_gates_json=data.get("default_gates") or ["initiation", "planning", "execution", "closure"],
        created_by_id=actor.id,
    )
    db.session.add(tpl)
    db.session.commit()
    return jsonify({"ok": True, "template": tpl.to_dict()}), 201


@project_templates_api.route("/<int:tpl_id>/instantiate", methods=["POST"])
@login_required
def instantiate_project_template(tpl_id: int):
    actor = _actor()
    org_id = actor.organization_id
    tpl = ProjectTemplate.query.filter_by(id=tpl_id, organization_id=org_id).first()
    if tpl is None:
        abort(404)
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or f"{tpl.name} Instance").strip()[:200]
    cnt = Project.query.filter_by(organization_id=org_id).count()
    proj = Project(
        organization_id=org_id,
        project_code=f"PRJ-{datetime.utcnow().year}-{cnt + 1:03d}",
        name=name,
        description=f"Instantiated from template {tpl.code} v{tpl.version}",
        category=tpl.category,
        delivery_methodology=tpl.delivery_methodology,
        owner_user_id=actor.id,
        sponsor_user_id=actor.id,
        lifecycle_state="planning",
        status="active",
        budget_numeric=to_decimal(data.get("budget_amount")) if data.get("budget_amount") not in (None, "") else None,
        budget_amount=float(to_decimal(data.get("budget_amount"))) if data.get("budget_amount") not in (None, "") else None,
        currency=str(data.get("currency") or "USD").strip()[:12],
    )
    db.session.add(proj)
    db.session.flush()
    db.session.add(ProjectMembership(
        organization_id=org_id, project_id=proj.id, user_id=actor.id,
        project_role="project_manager", can_view_finance=True, is_active=True, granted_by_id=actor.id,
    ))
    for idx, w in enumerate(tpl.default_wbs_json or []):
        db.session.add(ProjectWBSNode(
            organization_id=org_id, project_id=proj.id,
            wbs_code=str(w.get("wbs_code") or f"{idx + 1}.0")[:32],
            title=str(w.get("title") or "Work Package")[:220],
            weight_pct=max(0, min(100, int(w.get("weight_pct") or 0))),
            sort_order=idx,
            owner_user_id=actor.id,
        ))
    for st in (tpl.default_gates_json or []):
        db.session.add(ProjectGate(organization_id=org_id, project_id=proj.id, stage=str(st)[:32], gate_state="not_ready"))
    db.session.commit()
    return jsonify({"ok": True, "project": proj.to_dict(), "template_version": tpl.version}), 201


# =====================================================================
# PM-32: CSV DRY-RUN IMPORT & FORMULA-SAFE EXPORT
# =====================================================================

@projects_batch3_api.route("/<int:project_id>/import-tasks", methods=["POST"])
@login_required
def import_project_tasks_csv(project_id: int):
    """Import tasks from CSV with dry-run validation before commit."""
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    assert_project_mutable(proj)
    data = request.get_json(silent=True) or {}
    csv_text = str(data.get("csv_text") or "")
    dry_run = bool(data.get("dry_run", True))
    if not csv_text.strip():
        return jsonify({"error": "csv_text is required"}), 422

    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    errors = []
    valid_rows = []
    for idx, row in enumerate(reader, start=2):
        title = str(row.get("title") or "").strip()[:220]
        if not title:
            errors.append({"row": idx, "error": "Missing required 'title'"})
            continue
        prio = str(row.get("priority") or "medium").strip().lower()
        if prio not in ("low", "medium", "high", "critical", "urgent"):
            errors.append({"row": idx, "error": f"Invalid priority '{prio}'"})
            continue
        valid_rows.append({
            "title": title,
            "phase": str(row.get("phase") or "Execution").strip()[:64],
            "priority": prio,
            "due_date": str(row.get("due_date") or "").strip()[:32] or None,
        })

    if dry_run or errors:
        return jsonify({
            "ok": len(errors) == 0,
            "dry_run": dry_run,
            "valid_count": len(valid_rows),
            "errors": errors,
        }), (200 if len(errors) == 0 else 422)

    created = 0
    for r in valid_rows:
        db.session.add(ProjectTask(
            organization_id=proj.organization_id,
            project_id=proj.id,
            title=r["title"],
            phase=r["phase"],
            priority=r["priority"],
            status="todo",
            due_date=r["due_date"],
            due_date_typed=parse_iso_date(r["due_date"]),
            created_by_id=actor.id,
        ))
        created += 1
    db.session.commit()
    return jsonify({"ok": True, "dry_run": False, "imported_count": created}), 201


@projects_batch3_api.route("/<int:project_id>/export.csv", methods=["GET"])
@login_required
def export_project_tasks_csv(project_id: int):
    """Export project tasks to CSV with formula-injection neutralization."""
    actor = _actor()
    proj = load_authorized_project(project_id, actor)
    tasks = ProjectTask.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).order_by(ProjectTask.id.asc()).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["task_id", "title", "phase", "priority", "status", "due_date", "progress_pct"])
    for t in tasks:
        writer.writerow([
            t.id,
            _csv_safe(t.title),
            _csv_safe(t.phase),
            _csv_safe(t.priority),
            _csv_safe(t.status),
            _csv_safe(t.due_date or ""),
            t.progress_pct,
        ])
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{proj.project_code}_tasks.csv"'},
    )
