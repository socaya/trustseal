"""Batch 2 Enterprise Project Management REST APIs (PM-05, 09, 11, 14, 17, 21, 22, 24, 26, 30)."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from flask import Blueprint, abort, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.project_enterprise_ext import (
    OrgResourceProfile,
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
from app.models.project_management import ProjectCostEvent, parse_iso_date, to_decimal
from app.models.tsd_document import TSDocument
from app.blueprints.projects.permissions import (
    assert_project_mutable,
    can_approve_project_governance,
    can_view_project_finance,
    is_org_or_platform_admin,
    load_authorized_project,
)
from app.blueprints.projects.services import emit_project_event

resources_api = Blueprint("resources_api", __name__, url_prefix="/api/resources")
projects_batch2_api = Blueprint("projects_batch2_api", __name__, url_prefix="/api/projects")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _actor():
    if not current_user.is_authenticated:
        abort(401)
    if current_user.organization_id is None:
        abort(403, description="organization_required")
    return current_user


# =====================================================================
# PM-11: ORGANIZATION RESOURCE POOL & SKILLS (/api/resources)
# =====================================================================

@resources_api.route("", methods=["GET", "POST"])
@resources_api.route("/", methods=["GET", "POST"])
@login_required
def org_resources_collection():
    actor = _actor()
    org_id = actor.organization_id
    show_rates = is_org_or_platform_admin(actor)

    if request.method == "GET":
        rows = OrgResourceProfile.query.filter_by(organization_id=org_id).order_by(OrgResourceProfile.display_name.asc()).all()
        return jsonify({"ok": True, "resources": [r.to_dict(include_rates=show_rates) for r in rows]})

    data = request.get_json(silent=True) or {}
    name = str(data.get("display_name") or "").strip()[:160]
    if not name:
        return jsonify({"error": "display_name is required"}), 422
    prof = OrgResourceProfile(
        organization_id=org_id,
        user_id=int(data["user_id"]) if str(data.get("user_id") or "").isdigit() else None,
        display_name=name,
        resource_type=str(data.get("resource_type") or "employee").strip()[:24],
        department=str(data.get("department") or "").strip()[:120] or None,
        skills_csv=str(data.get("skills_csv") or ",".join(data.get("skills") or [])).strip()[:400] or None,
        certification_name=str(data.get("certification_name") or "").strip()[:160] or None,
        certification_expiry_date=parse_iso_date(data.get("certification_expiry_date")),
        standard_hourly_rate=to_decimal(data.get("standard_hourly_rate")) if data.get("standard_hourly_rate") not in (None, "") else None,
        currency=str(data.get("currency") or "USD").strip()[:12],
        availability_pct=max(0, min(100, int(data.get("availability_pct") or 100))),
        is_active=bool(data.get("is_active", True)),
    )
    db.session.add(prof)
    db.session.commit()
    return jsonify({"ok": True, "resource": prof.to_dict(include_rates=show_rates)}), 201


# =====================================================================
# PM-05: SCOPE & REQUIREMENTS TRACEABILITY
# =====================================================================

@projects_batch2_api.route("/<int:project_id>/requirements", methods=["GET", "POST"])
@login_required
def project_requirements_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))

    if request.method == "GET":
        rows = ProjectRequirement.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).order_by(ProjectRequirement.id.desc()).all()
        return jsonify({"ok": True, "requirements": [r.to_dict() for r in rows]})

    assert_project_mutable(proj)
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()[:220]
    if not title:
        return jsonify({"error": "Requirement title is required"}), 422
    cnt = ProjectRequirement.query.filter_by(project_id=proj.id).count()
    req = ProjectRequirement(
        organization_id=proj.organization_id,
        project_id=proj.id,
        req_code=str(data.get("req_code") or f"REQ-{cnt + 1:03d}").strip()[:40],
        title=title,
        category=str(data.get("category") or "business").strip()[:32],
        priority=str(data.get("priority") or "must").strip()[:16],
        acceptance_criteria=str(data.get("acceptance_criteria") or "").strip() or None,
        wbs_node_id=int(data["wbs_node_id"]) if str(data.get("wbs_node_id") or "").isdigit() else None,
        linked_task_id=int(data["linked_task_id"]) if str(data.get("linked_task_id") or "").isdigit() else None,
        status="draft",
        version=1,
        created_by_id=actor.id,
    )
    db.session.add(req)
    db.session.commit()
    return jsonify({"ok": True, "requirement": req.to_dict()}), 201


@projects_batch2_api.route("/<int:project_id>/requirements/<int:req_id>/approve", methods=["POST"])
@login_required
def approve_project_requirement(project_id: int, req_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    req = ProjectRequirement.query.filter_by(id=req_id, project_id=proj.id, organization_id=proj.organization_id).first()
    if req is None:
        abort(404)
    req.status = "approved"
    req.approved_by_id = actor.id
    req.approved_at = _utcnow()
    db.session.commit()
    return jsonify({"ok": True, "requirement": req.to_dict()})


@projects_batch2_api.route("/<int:project_id>/requirements/<int:req_id>", methods=["PATCH"])
@login_required
def update_project_requirement(project_id: int, req_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    assert_project_mutable(proj)
    req = ProjectRequirement.query.filter_by(id=req_id, project_id=proj.id, organization_id=proj.organization_id).first()
    if req is None:
        abort(404)
    # Spec PM-05: approved requirements cannot be overwritten in place
    if req.status == "approved":
        return jsonify({"error": "Approved requirement cannot be overwritten in place; create a new version"}), 409
    data = request.get_json(silent=True) or {}
    if "title" in data and str(data["title"]).strip():
        req.title = str(data["title"]).strip()[:220]
    if "acceptance_criteria" in data:
        req.acceptance_criteria = str(data["acceptance_criteria"] or "").strip() or None
    db.session.commit()
    return jsonify({"ok": True, "requirement": req.to_dict()})


# =====================================================================
# PM-09: AGILE SPRINTS & BACKLOG
# =====================================================================

@projects_batch2_api.route("/<int:project_id>/sprints", methods=["GET", "POST"])
@login_required
def project_sprints_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))

    if request.method == "GET":
        rows = ProjectSprint.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).order_by(ProjectSprint.id.desc()).all()
        return jsonify({"ok": True, "sprints": [r.to_dict() for r in rows]})

    assert_project_mutable(proj)
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()[:120]
    if not name:
        return jsonify({"error": "Sprint name is required"}), 422
    sp = ProjectSprint(
        organization_id=proj.organization_id,
        project_id=proj.id,
        name=name,
        goal=str(data.get("goal") or "").strip()[:300] or None,
        start_date=parse_iso_date(data.get("start_date")),
        end_date=parse_iso_date(data.get("end_date")),
        capacity_points=max(0, int(data.get("capacity_points") or 30)),
        status=str(data.get("status") or "active").strip()[:24],
    )
    db.session.add(sp)
    db.session.commit()
    return jsonify({"ok": True, "sprint": sp.to_dict()}), 201


@projects_batch2_api.route("/<int:project_id>/sprints/<int:sprint_id>/complete", methods=["POST"])
@login_required
def complete_project_sprint(project_id: int, sprint_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    sp = ProjectSprint.query.filter_by(id=sprint_id, project_id=proj.id, organization_id=proj.organization_id).first()
    if sp is None:
        abort(404)
    items = ProjectBacklogItem.query.filter_by(project_id=proj.id, sprint_id=sp.id).all()
    done_pts = sum(int(i.story_points or 0) for i in items if i.status == "done")
    carryover = sum(1 for i in items if i.status != "done")
    sp.completed_points = done_pts
    sp.status = "completed"
    sp.completed_at = _utcnow()
    db.session.commit()
    return jsonify({"ok": True, "sprint": sp.to_dict(), "velocity_points": done_pts, "carryover_count": carryover})


@projects_batch2_api.route("/<int:project_id>/backlog", methods=["GET", "POST"])
@login_required
def project_backlog_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))

    if request.method == "GET":
        rows = ProjectBacklogItem.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).order_by(ProjectBacklogItem.id.desc()).all()
        return jsonify({"ok": True, "backlog": [r.to_dict() for r in rows]})

    assert_project_mutable(proj)
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()[:220]
    if not title:
        return jsonify({"error": "Backlog item title is required"}), 422
    item = ProjectBacklogItem(
        organization_id=proj.organization_id,
        project_id=proj.id,
        sprint_id=int(data["sprint_id"]) if str(data.get("sprint_id") or "").isdigit() else None,
        requirement_id=int(data["requirement_id"]) if str(data.get("requirement_id") or "").isdigit() else None,
        item_type=str(data.get("item_type") or "story").strip()[:24],
        title=title,
        story_points=max(0, int(data.get("story_points") or 3)),
        priority=str(data.get("priority") or "medium").strip()[:16],
        status=str(data.get("status") or "backlog").strip()[:24],
        assignee_user_id=int(data["assignee_user_id"]) if str(data.get("assignee_user_id") or "").isdigit() else None,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({"ok": True, "item": item.to_dict()}), 201


@projects_batch2_api.route("/<int:project_id>/backlog/<int:item_id>", methods=["PATCH"])
@login_required
def update_backlog_item(project_id: int, item_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    item = ProjectBacklogItem.query.filter_by(id=item_id, project_id=proj.id, organization_id=proj.organization_id).first()
    if item is None:
        abort(404)
    data = request.get_json(silent=True) or {}
    if "status" in data:
        item.status = str(data["status"]).strip()[:24]
    if "sprint_id" in data:
        item.sprint_id = int(data["sprint_id"]) if str(data["sprint_id"] or "").isdigit() else None
    if "story_points" in data:
        item.story_points = max(0, int(data["story_points"] or 0))
    db.session.commit()
    return jsonify({"ok": True, "item": item.to_dict()})


# =====================================================================
# PM-14: EQUIPMENT, MATERIALS & LOGISTICS
# =====================================================================

@projects_batch2_api.route("/<int:project_id>/assets", methods=["GET", "POST"])
@login_required
def project_assets_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))

    if request.method == "GET":
        rows = ProjectAssetBooking.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).order_by(ProjectAssetBooking.id.desc()).all()
        return jsonify({"ok": True, "assets": [r.to_dict() for r in rows]})

    assert_project_mutable(proj)
    data = request.get_json(silent=True) or {}
    name = str(data.get("asset_name") or "").strip()[:180]
    sd = parse_iso_date(data.get("start_date"))
    ed = parse_iso_date(data.get("end_date"))
    if not name or not sd or not ed or ed < sd:
        return jsonify({"error": "asset_name, start_date, and end_date (end >= start) are required"}), 422
    exclusive = bool(data.get("exclusive", True))
    if exclusive:
        overlap = ProjectAssetBooking.query.filter(
            ProjectAssetBooking.organization_id == proj.organization_id,
            ProjectAssetBooking.asset_name == name,
            ProjectAssetBooking.exclusive.is_(True),
            ProjectAssetBooking.status.in_(("booked", "issued")),
            ProjectAssetBooking.start_date <= ed,
            ProjectAssetBooking.end_date >= sd,
        ).first()
        if overlap is not None:
            return jsonify({"error": f"Exclusive asset '{name}' already booked for overlapping dates ({overlap.start_date} to {overlap.end_date})"}), 409

    booking = ProjectAssetBooking(
        organization_id=proj.organization_id,
        project_id=proj.id,
        asset_name=name,
        asset_type=str(data.get("asset_type") or "equipment").strip()[:24],
        exclusive=exclusive,
        quantity=to_decimal(data.get("quantity"), "1.00"),
        unit=str(data.get("unit") or "unit").strip()[:24],
        unit_cost=to_decimal(data.get("unit_cost")) if data.get("unit_cost") not in (None, "") else None,
        currency=str(data.get("currency") or proj.currency or "USD").strip()[:12],
        start_date=sd,
        end_date=ed,
        custodian_name=str(data.get("custodian_name") or "").strip()[:140] or None,
        status="booked",
        created_by_id=actor.id,
    )
    db.session.add(booking)
    db.session.commit()
    return jsonify({"ok": True, "asset": booking.to_dict()}), 201


# =====================================================================
# PM-17: PROCUREMENT & SUPPLIER MANAGEMENT (WITH SEPARATION OF DUTIES)
# =====================================================================

@projects_batch2_api.route("/<int:project_id>/procurement", methods=["GET", "POST"])
@login_required
def project_procurement_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))

    if request.method == "GET":
        rows = ProjectProcurement.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).order_by(ProjectProcurement.id.desc()).all()
        return jsonify({"ok": True, "procurements": [r.to_dict() for r in rows]})

    assert_project_mutable(proj)
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()[:220]
    if not title:
        return jsonify({"error": "Procurement title is required"}), 422
    cnt = ProjectProcurement.query.filter_by(project_id=proj.id).count()
    pr = ProjectProcurement(
        organization_id=proj.organization_id,
        project_id=proj.id,
        req_number=str(data.get("req_number") or f"PR-{cnt + 1:03d}").strip()[:40],
        title=title,
        supplier_name=str(data.get("supplier_name") or "").strip()[:180] or None,
        estimated_amount=to_decimal(data.get("estimated_amount")),
        currency=str(data.get("currency") or proj.currency or "USD").strip()[:12],
        status="requisition",
        requested_by_id=actor.id,
    )
    db.session.add(pr)
    db.session.commit()
    return jsonify({"ok": True, "procurement": pr.to_dict()}), 201


@projects_batch2_api.route("/<int:project_id>/procurement/<int:pr_id>/award", methods=["POST"])
@login_required
def award_project_procurement(project_id: int, pr_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    if not can_approve_project_governance(proj, actor):
        abort(403, description="procurement_award_permission_required")
    pr = ProjectProcurement.query.filter_by(id=pr_id, project_id=proj.id, organization_id=proj.organization_id).first()
    if pr is None:
        abort(404)
    data = request.get_json(silent=True) or {}
    # Separation of duties: requester cannot approve own award when enforce_sod is True
    if data.get("enforce_sod") and pr.requested_by_id == actor.id:
        return jsonify({"error": "Separation of duties: requester cannot approve own procurement award"}), 403

    award_amt = to_decimal(data.get("awarded_amount") if data.get("awarded_amount") not in (None, "") else pr.estimated_amount)
    pr.awarded_amount = award_amt
    if data.get("supplier_name"):
        pr.supplier_name = str(data["supplier_name"]).strip()[:180]
    pr.status = "awarded"
    pr.approved_by_id = actor.id
    pr.awarded_at = _utcnow()

    # Post single idempotent commitment cost event to ledger
    sref = f"procurement:{pr.id}"
    ev = ProjectCostEvent.query.filter_by(organization_id=proj.organization_id, project_id=proj.id, source_ref=sref).first()
    if ev is None:
        ev = ProjectCostEvent(
            organization_id=proj.organization_id,
            project_id=proj.id,
            event_type="commitment",
            category="vendor",
            description=f"Procurement award {pr.req_number}: {pr.title}",
            amount=award_amt,
            currency=pr.currency or proj.currency or "USD",
            source_ref=sref,
            status="posted",
            event_date=_utcnow().date(),
            created_by_id=actor.id,
        )
        db.session.add(ev)
        db.session.flush()
    pr.commitment_cost_event_id = ev.id
    emit_project_event(
        organization_id=proj.organization_id,
        actor_id=actor.id,
        event_type="procurement.awarded",
        aggregate_type="project_procurement",
        aggregate_id=pr.id,
        payload={"project_id": proj.id, "req_number": pr.req_number, "cost_event_id": ev.id},
    )
    db.session.commit()
    return jsonify({"ok": True, "procurement": pr.to_dict(), "cost_event": ev.to_dict()})


# =====================================================================
# PM-21: QUALITY MANAGEMENT & ASSURANCE
# =====================================================================

@projects_batch2_api.route("/<int:project_id>/quality", methods=["GET", "POST"])
@login_required
def project_quality_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))

    if request.method == "GET":
        rows = ProjectQualityRecord.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).order_by(ProjectQualityRecord.id.desc()).all()
        return jsonify({"ok": True, "quality_records": [r.to_dict() for r in rows]})

    assert_project_mutable(proj)
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()[:220]
    if not title:
        return jsonify({"error": "Quality record title is required"}), 422
    rec = ProjectQualityRecord(
        organization_id=proj.organization_id,
        project_id=proj.id,
        record_type=str(data.get("record_type") or "inspection").strip()[:24],
        title=title,
        severity=str(data.get("severity") or "medium").strip()[:16],
        wbs_node_id=int(data["wbs_node_id"]) if str(data.get("wbs_node_id") or "").isdigit() else None,
        requirement_id=int(data["requirement_id"]) if str(data.get("requirement_id") or "").isdigit() else None,
        evidence_notes=str(data.get("evidence_notes") or "").strip() or None,
        status=str(data.get("status") or "open").strip()[:24],
        created_by_id=actor.id,
    )
    db.session.add(rec)
    db.session.commit()
    return jsonify({"ok": True, "quality_record": rec.to_dict()}), 201


@projects_batch2_api.route("/<int:project_id>/quality/<int:qid>", methods=["PATCH"])
@login_required
def update_quality_record(project_id: int, qid: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    rec = ProjectQualityRecord.query.filter_by(id=qid, project_id=proj.id, organization_id=proj.organization_id).first()
    if rec is None:
        abort(404)
    data = request.get_json(silent=True) or {}
    if "status" in data:
        rec.status = str(data["status"]).strip()[:24]
    if "evidence_notes" in data:
        rec.evidence_notes = str(data["evidence_notes"] or "").strip() or None
    db.session.commit()
    return jsonify({"ok": True, "quality_record": rec.to_dict()})


# =====================================================================
# PM-22: STAKEHOLDERS & COMMUNICATIONS
# =====================================================================

@projects_batch2_api.route("/<int:project_id>/stakeholders", methods=["GET", "POST"])
@login_required
def project_stakeholders_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))

    if request.method == "GET":
        rows = ProjectStakeholder.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).order_by(ProjectStakeholder.id.desc()).all()
        return jsonify({"ok": True, "stakeholders": [r.to_dict() for r in rows]})

    assert_project_mutable(proj)
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()[:160]
    if not name:
        return jsonify({"error": "Stakeholder name is required"}), 422
    st = ProjectStakeholder(
        organization_id=proj.organization_id,
        project_id=proj.id,
        name=name,
        organization_name=str(data.get("organization_name") or "").strip()[:160] or None,
        role_title=str(data.get("role_title") or "").strip()[:120] or None,
        email=str(data.get("email") or "").strip()[:180] or None,
        influence_level=str(data.get("influence_level") or "medium").strip()[:16],
        interest_level=str(data.get("interest_level") or "medium").strip()[:16],
        comms_cadence=str(data.get("comms_cadence") or "monthly").strip()[:24],
        engagement_strategy=str(data.get("engagement_strategy") or "").strip()[:240] or None,
        is_external=bool(data.get("is_external", False)),
    )
    db.session.add(st)
    db.session.commit()
    return jsonify({"ok": True, "stakeholder": st.to_dict()}), 201


# =====================================================================
# PM-24: PROJECT DOCUMENT LINKS (IMMUTABLE TSD VERSIONS)
# =====================================================================

@projects_batch2_api.route("/<int:project_id>/documents", methods=["GET", "POST"])
@login_required
def project_documents_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))

    if request.method == "GET":
        rows = ProjectDocumentLink.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).order_by(ProjectDocumentLink.id.desc()).all()
        dids = [r.document_id for r in rows]
        docs = {d.id: d for d in TSDocument.query.filter(TSDocument.id.in_(dids)).all()} if dids else {}
        out = [{**r.to_dict(), "title": docs[r.document_id].title if r.document_id in docs else f"Doc #{r.document_id}"} for r in rows]
        return jsonify({"ok": True, "documents": out})

    assert_project_mutable(proj)
    data = request.get_json(silent=True) or {}
    did = data.get("document_id")
    if not str(did or "").isdigit():
        return jsonify({"error": "document_id is required"}), 422
    doc = TSDocument.query.filter_by(id=int(did), organization_id=proj.organization_id).filter(TSDocument.deleted_at.is_(None)).first()
    if doc is None:
        return jsonify({"error": "TSD document not found in organization"}), 404
    ver = int(data.get("pinned_version") or doc.version or 1)
    link = ProjectDocumentLink(
        organization_id=proj.organization_id,
        project_id=proj.id,
        document_id=doc.id,
        pinned_version=ver,
        classification=str(data.get("classification") or "deliverable").strip()[:32],
        retention_rule=str(data.get("retention_rule") or "7_years").strip()[:64],
        linked_by_id=actor.id,
    )
    db.session.add(link)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Document version already linked to project"}), 409
    return jsonify({"ok": True, "document_link": {**link.to_dict(), "title": doc.title}}), 201


# =====================================================================
# PM-26: MONITORING, EVALUATION & RESULTS FRAMEWORK (M&E)
# =====================================================================

@projects_batch2_api.route("/<int:project_id>/indicators", methods=["GET", "POST"])
@login_required
def project_indicators_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))

    if request.method == "GET":
        inds = ProjectIndicator.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).order_by(ProjectIndicator.id.asc()).all()
        obs = ProjectIndicatorObservation.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).all()
        obs_by_ind: dict[int, list[ProjectIndicatorObservation]] = {}
        for o in obs:
            obs_by_ind.setdefault(o.indicator_id, []).append(o)
        out = []
        for ind in inds:
            # Spec PM-26: rejected data excluded; missing data is None (not 0)
            valid_obs = [o for o in obs_by_ind.get(ind.id, []) if o.status == "validated"]
            latest_val = str(valid_obs[-1].observed_value) if valid_obs else None
            out.append({
                **ind.to_dict(),
                "latest_validated_value": latest_val,
                "observations": [o.to_dict() for o in obs_by_ind.get(ind.id, [])],
            })
        return jsonify({"ok": True, "indicators": out})

    assert_project_mutable(proj)
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()[:220]
    if not title:
        return jsonify({"error": "Indicator title is required"}), 422
    cnt = ProjectIndicator.query.filter_by(project_id=proj.id).count()
    ind = ProjectIndicator(
        organization_id=proj.organization_id,
        project_id=proj.id,
        indicator_code=str(data.get("indicator_code") or f"IND-{cnt + 1:03d}").strip()[:40],
        level=str(data.get("level") or "output").strip()[:24],
        title=title,
        unit=str(data.get("unit") or "count").strip()[:32],
        baseline_value=to_decimal(data.get("baseline_value")) if data.get("baseline_value") not in (None, "") else None,
        target_value=to_decimal(data.get("target_value")) if data.get("target_value") not in (None, "") else None,
        owner_name=str(data.get("owner_name") or "").strip()[:120] or None,
    )
    db.session.add(ind)
    db.session.commit()
    return jsonify({"ok": True, "indicator": ind.to_dict()}), 201


@projects_batch2_api.route("/<int:project_id>/indicators/<int:ind_id>/observations", methods=["POST"])
@login_required
def add_indicator_observation(project_id: int, ind_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    ind = ProjectIndicator.query.filter_by(id=ind_id, project_id=proj.id, organization_id=proj.organization_id).first()
    if ind is None:
        abort(404)
    data = request.get_json(silent=True) or {}
    period = str(data.get("period_label") or "").strip()[:40]
    if not period:
        return jsonify({"error": "period_label is required"}), 422
    num = to_decimal(data.get("numerator")) if data.get("numerator") not in (None, "") else None
    den = to_decimal(data.get("denominator")) if data.get("denominator") not in (None, "") else None
    # Spec PM-26: invalid/zero denominator rejected
    if den is not None and den <= Decimal("0.00"):
        return jsonify({"error": "denominator must be greater than zero"}), 422
    if num is not None and den is not None:
        obs_val = ((num / den) * Decimal("100")).quantize(Decimal("0.01"))
    elif data.get("observed_value") not in (None, ""):
        obs_val = to_decimal(data.get("observed_value"))
    else:
        return jsonify({"error": "observed_value or numerator/denominator required"}), 422

    obs = ProjectIndicatorObservation(
        organization_id=proj.organization_id,
        project_id=proj.id,
        indicator_id=ind.id,
        period_label=period,
        numerator=num,
        denominator=den,
        observed_value=obs_val,
        evidence_note=str(data.get("evidence_note") or "").strip() or None,
        status="draft",
    )
    db.session.add(obs)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": f"Duplicate observation for period '{period}'"}), 409
    return jsonify({"ok": True, "observation": obs.to_dict()}), 201


@projects_batch2_api.route("/<int:project_id>/observations/<int:obs_id>/validate", methods=["POST"])
@login_required
def validate_indicator_observation(project_id: int, obs_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    obs = ProjectIndicatorObservation.query.filter_by(id=obs_id, project_id=proj.id, organization_id=proj.organization_id).first()
    if obs is None:
        abort(404)
    data = request.get_json(silent=True) or {}
    st = str(data.get("status") or "validated").strip().lower()
    if st not in ("validated", "rejected"):
        return jsonify({"error": "status must be validated or rejected"}), 422
    obs.status = st
    obs.validated_by_id = actor.id
    obs.validated_at = _utcnow()
    if st == "validated":
        emit_project_event(
            organization_id=proj.organization_id,
            actor_id=actor.id,
            event_type="indicator.published",
            aggregate_type="project_indicator_observation",
            aggregate_id=obs.id,
            payload={"project_id": proj.id, "indicator_id": obs.indicator_id, "period": obs.period_label},
        )
    db.session.commit()
    return jsonify({"ok": True, "observation": obs.to_dict()})


# =====================================================================
# PM-30: HANDOVER, CLOSURE CHECKLIST & BENEFITS REALIZATION
# =====================================================================

@projects_batch2_api.route("/<int:project_id>/closure", methods=["GET", "POST"])
@login_required
def project_closure_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))

    if request.method == "GET":
        rows = ProjectClosureItem.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).order_by(ProjectClosureItem.id.asc()).all()
        return jsonify({"ok": True, "closure_items": [r.to_dict() for r in rows]})

    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()[:220]
    if not title:
        return jsonify({"error": "Closure item title is required"}), 422
    item = ProjectClosureItem(
        organization_id=proj.organization_id,
        project_id=proj.id,
        category=str(data.get("category") or "handover").strip()[:32],
        title=title,
        is_mandatory=bool(data.get("is_mandatory", True)),
        evidence_note=str(data.get("evidence_note") or "").strip() or None,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({"ok": True, "closure_item": item.to_dict()}), 201


@projects_batch2_api.route("/<int:project_id>/closure/<int:cid>", methods=["PATCH"])
@login_required
def update_closure_item(project_id: int, cid: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    item = ProjectClosureItem.query.filter_by(id=cid, project_id=proj.id, organization_id=proj.organization_id).first()
    if item is None:
        abort(404)
    data = request.get_json(silent=True) or {}
    if "completed" in data:
        item.completed = bool(data["completed"])
        item.completed_by_id = actor.id if item.completed else None
        item.completed_at = _utcnow() if item.completed else None
    if "evidence_note" in data:
        item.evidence_note = str(data["evidence_note"] or "").strip() or None
    db.session.commit()
    return jsonify({"ok": True, "closure_item": item.to_dict()})


@projects_batch2_api.route("/<int:project_id>/benefits", methods=["GET", "POST"])
@login_required
def project_benefits_collection(project_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=(request.method == "POST"))

    if request.method == "GET":
        rows = ProjectBenefit.query.filter_by(organization_id=proj.organization_id, project_id=proj.id).order_by(ProjectBenefit.id.asc()).all()
        return jsonify({"ok": True, "benefits": [r.to_dict() for r in rows]})

    # Spec Section 4: Benefits updates are permitted even after project closure!
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()[:220]
    if not title:
        return jsonify({"error": "Benefit title is required"}), 422
    ben = ProjectBenefit(
        organization_id=proj.organization_id,
        project_id=proj.id,
        benefit_type=str(data.get("benefit_type") or "operational").strip()[:24],
        title=title,
        target_value=str(data.get("target_value") or "").strip()[:120] or None,
        realized_value=str(data.get("realized_value") or "").strip()[:120] or None,
        review_date=parse_iso_date(data.get("review_date")),
        owner_name=str(data.get("owner_name") or "").strip()[:120] or None,
        status=str(data.get("status") or "planned").strip()[:24],
    )
    db.session.add(ben)
    db.session.commit()
    return jsonify({"ok": True, "benefit": ben.to_dict()}), 201
