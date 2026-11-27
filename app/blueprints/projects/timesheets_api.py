"""Enterprise Project Timesheets API v2.1 (PM-13.01..PM-13.16).

Provides:
- ``GET /api/timesheets`` — Consolidated personal timesheet across authorized projects
- ``POST /api/projects/<id>/timesheets/<eid>/submit`` — Submit draft/returned entry
- ``POST /api/projects/<id>/timesheets/<eid>/withdraw`` — Withdraw submitted entry before approval
- ``POST /api/projects/<id>/timesheets/<eid>/return`` — Return/reject entry with mandatory reason
- ``POST /api/projects/<id>/timesheets/<eid>/adjust`` — Immutable adjustment/reversal posting delta cost
- ``POST /api/projects/<id>/timesheets/<eid>/lock`` — Lock approved entry
- ``GET /api/projects/<id>/timesheets/export.csv`` — Formula-safe CSV export with totals
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from decimal import Decimal

from flask import Blueprint, Response, abort, jsonify, request
from flask_login import current_user, login_required

from app.extensions import db
from app.models.contract_workflow import Project
from app.models.project_management import (
    ProjectCostEvent,
    ProjectTimeAdjustment,
    ProjectTimeEntry,
    to_decimal,
)
from app.blueprints.projects.permissions import (
    assert_project_mutable,
    can_approve_project_governance,
    can_view_project_finance,
    load_authorized_project,
)
from app.blueprints.projects.services import emit_project_event

timesheets_v21_api = Blueprint("timesheets_v21_api", __name__, url_prefix="/api/timesheets")
project_timesheets_v21_api = Blueprint("project_timesheets_v21_api", __name__, url_prefix="/api/projects")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _actor():
    if not current_user.is_authenticated:
        abort(401)
    if current_user.organization_id is None:
        abort(403, description="organization_required")
    return current_user


def _csv_safe(val: object) -> str:
    s = str(val if val is not None else "")
    return ("'" + s) if (s and s[0] in ("=", "+", "-", "@", "\t", "\r")) else s


@timesheets_v21_api.route("", methods=["GET"])
@timesheets_v21_api.route("/", methods=["GET"])
@login_required
def my_consolidated_timesheet():
    """PM-13.03: Consolidated personal timesheet across all authorized projects."""
    actor = _actor()
    entries = (
        ProjectTimeEntry.query.filter_by(organization_id=actor.organization_id, user_id=actor.id)
        .order_by(ProjectTimeEntry.work_date.desc(), ProjectTimeEntry.id.desc())
        .all()
    )
    pids = list({e.project_id for e in entries})
    projs = {p.id: p for p in Project.query.filter(Project.id.in_(pids)).all()} if pids else {}
    total_hrs = sum((Decimal(e.hours or 0) for e in entries), Decimal("0.00"))
    billable_hrs = sum((Decimal(e.hours or 0) for e in entries if e.billable), Decimal("0.00"))
    ratio = (
        str(((billable_hrs / total_hrs) * Decimal("100")).quantize(Decimal("0.01")))
        if total_hrs > Decimal("0.00")
        else None
    )
    return jsonify({
        "ok": True,
        "summary": {
            "total_hours": str(total_hrs.quantize(Decimal("0.01"))),
            "billable_hours": str(billable_hrs.quantize(Decimal("0.01"))),
            "billable_ratio_pct": ratio,
        },
        "entries": [
            {**e.to_dict(include_rates=False), "project_name": projs[e.project_id].name if e.project_id in projs else ""}
            for e in entries
        ],
    })


@project_timesheets_v21_api.route("/<int:project_id>/timesheets/<int:entry_id>/submit", methods=["POST"])
@login_required
def submit_time_entry(project_id: int, entry_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    assert_project_mutable(proj)
    entry = ProjectTimeEntry.query.filter_by(id=entry_id, project_id=proj.id, organization_id=proj.organization_id).first()
    if entry is None:
        abort(404)
    if entry.user_id != actor.id and not can_approve_project_governance(proj, actor):
        abort(403)
    if entry.status in ("approved", "locked"):
        return jsonify({"error": "Approved/locked entry cannot be resubmitted"}), 409
    entry.status = "submitted"
    entry.return_reason = None
    emit_project_event(
        organization_id=proj.organization_id,
        actor_id=actor.id,
        event_type="timesheet.submitted",
        aggregate_type="project_time_entry",
        aggregate_id=entry.id,
        payload={"project_id": proj.id, "hours": str(entry.hours)},
    )
    db.session.commit()
    return jsonify({"ok": True, "time_entry": entry.to_dict(include_rates=can_view_project_finance(proj, actor))})


@project_timesheets_v21_api.route("/<int:project_id>/timesheets/<int:entry_id>/withdraw", methods=["POST"])
@login_required
def withdraw_time_entry(project_id: int, entry_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    entry = ProjectTimeEntry.query.filter_by(id=entry_id, project_id=proj.id, organization_id=proj.organization_id).first()
    if entry is None:
        abort(404)
    if entry.status != "submitted":
        return jsonify({"error": "Only submitted entries can be withdrawn before approval"}), 409
    entry.status = "draft"
    db.session.commit()
    return jsonify({"ok": True, "time_entry": entry.to_dict(include_rates=can_view_project_finance(proj, actor))})


@project_timesheets_v21_api.route("/<int:project_id>/timesheets/<int:entry_id>/return", methods=["POST"])
@login_required
def return_time_entry(project_id: int, entry_id: int):
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    if not can_approve_project_governance(proj, actor):
        abort(403, description="timesheet_review_permission_required")
    entry = ProjectTimeEntry.query.filter_by(id=entry_id, project_id=proj.id, organization_id=proj.organization_id).first()
    if entry is None:
        abort(404)
    if entry.status in ("approved", "locked"):
        return jsonify({"error": "Approved entry is immutable; use /adjust for corrections"}), 409
    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason") or "").strip()[:400]
    if not reason:
        return jsonify({"error": "Return/rejection reason is required (PM-13.06)"}), 422
    entry.status = "returned"
    entry.return_reason = reason
    emit_project_event(
        organization_id=proj.organization_id,
        actor_id=actor.id,
        event_type="timesheet.returned",
        aggregate_type="project_time_entry",
        aggregate_id=entry.id,
        payload={"project_id": proj.id},
    )
    db.session.commit()
    return jsonify({"ok": True, "time_entry": entry.to_dict(include_rates=can_view_project_finance(proj, actor))})


@project_timesheets_v21_api.route("/<int:project_id>/timesheets/<int:entry_id>/adjust", methods=["POST"])
@login_required
def adjust_approved_time_entry(project_id: int, entry_id: int):
    """PM-13.08: Immutable adjustment/reversal linked to an approved time entry."""
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    if not can_approve_project_governance(proj, actor):
        abort(403, description="timesheet_adjustment_permission_required")
    entry = ProjectTimeEntry.query.filter_by(id=entry_id, project_id=proj.id, organization_id=proj.organization_id).first()
    if entry is None:
        abort(404)
    if entry.status != "approved":
        return jsonify({"error": "Only approved entries require linked adjustments"}), 409
    if entry.locked_at is not None:
        return jsonify({"error": "Entry is locked in a closed period; audited reopen required"}), 409

    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason") or "").strip()[:400]
    if not reason:
        return jsonify({"error": "Adjustment reason is required"}), 422
    delta_hrs = to_decimal(data.get("delta_hours"))
    if delta_hrs == Decimal("0.00"):
        return jsonify({"error": "delta_hours must be non-zero"}), 422

    rate = Decimal(entry.hourly_rate_snapshot or 0)
    delta_cost = (delta_hrs * rate).quantize(Decimal("0.01"))

    adj = ProjectTimeAdjustment(
        organization_id=proj.organization_id,
        project_id=proj.id,
        original_entry_id=entry.id,
        delta_hours=delta_hrs,
        delta_cost_amount=delta_cost,
        reason=reason,
        created_by_id=actor.id,
    )
    db.session.add(adj)
    db.session.flush()

    ev = ProjectCostEvent(
        organization_id=proj.organization_id,
        project_id=proj.id,
        event_type="reversal" if delta_cost < Decimal("0.00") else "actual",
        category="labor",
        description=f"Timesheet adjustment #{adj.id} for entry #{entry.id} ({delta_hrs}h): {reason[:120]}",
        amount=abs(delta_cost),
        currency=entry.currency or proj.currency or "USD",
        source_ref=f"timesheet_adj:{adj.id}",
        status="posted",
        event_date=_utcnow().date(),
        created_by_id=actor.id,
    )
    db.session.add(ev)
    db.session.flush()
    adj.posted_cost_event_id = ev.id

    emit_project_event(
        organization_id=proj.organization_id,
        actor_id=actor.id,
        event_type="timesheet.corrected",
        aggregate_type="project_time_adjustment",
        aggregate_id=adj.id,
        payload={"project_id": proj.id, "original_entry_id": entry.id, "delta_hours": str(delta_hrs)},
    )
    db.session.commit()
    return jsonify({"ok": True, "adjustment": adj.to_dict(), "cost_event": ev.to_dict()}), 201


@project_timesheets_v21_api.route("/<int:project_id>/timesheets/<int:entry_id>/lock", methods=["POST"])
@login_required
def lock_approved_time_entry(project_id: int, entry_id: int):
    """PM-13.06/08: Lock an approved time entry against further adjustments."""
    actor = _actor()
    proj = load_authorized_project(project_id, actor, require_write=True)
    if not can_approve_project_governance(proj, actor):
        abort(403, description="timesheet_lock_permission_required")
    entry = ProjectTimeEntry.query.filter_by(id=entry_id, project_id=proj.id, organization_id=proj.organization_id).first()
    if entry is None:
        abort(404)
    if entry.status != "approved":
        return jsonify({"error": "Only approved entries can be locked"}), 409
    entry.locked_at = _utcnow()
    emit_project_event(
        organization_id=proj.organization_id,
        actor_id=actor.id,
        event_type="timesheet.locked",
        aggregate_type="project_time_entry",
        aggregate_id=entry.id,
        payload={"project_id": proj.id},
    )
    db.session.commit()
    return jsonify({"ok": True, "time_entry": entry.to_dict(include_rates=can_view_project_finance(proj, actor))})


@project_timesheets_v21_api.route("/<int:project_id>/timesheets/export.csv", methods=["GET"])
@login_required
def export_project_timesheets_csv(project_id: int):
    """PM-13.14: Role-scoped formula-safe CSV export with totals."""
    actor = _actor()
    proj = load_authorized_project(project_id, actor)
    show_rates = can_view_project_finance(proj, actor)
    rows = (
        ProjectTimeEntry.query.filter_by(organization_id=proj.organization_id, project_id=proj.id)
        .order_by(ProjectTimeEntry.work_date.asc(), ProjectTimeEntry.id.asc())
        .all()
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    header = ["entry_id", "work_date", "user_id", "hours", "billable", "status", "notes"]
    if show_rates:
        header.extend(["rate_snapshot", "cost_amount", "currency"])
    writer.writerow(header)
    tot_hrs = Decimal("0.00")
    tot_cost = Decimal("0.00")
    for r in rows:
        tot_hrs += Decimal(r.hours or 0)
        tot_cost += Decimal(r.cost_amount or 0)
        line = [r.id, r.work_date.isoformat() if r.work_date else "", r.user_id, str(r.hours), r.billable, r.status, _csv_safe(r.notes or "")]
        if show_rates:
            line.extend([str(r.hourly_rate_snapshot or ""), str(r.cost_amount or ""), r.currency])
        writer.writerow(line)
    total_row = ["TOTAL", "", "", str(tot_hrs.quantize(Decimal("0.01"))), "", "", ""]
    if show_rates:
        total_row.extend(["", str(tot_cost.quantize(Decimal("0.01"))), proj.currency or "USD"])
    writer.writerow(total_row)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{proj.project_code}_timesheets.csv"'},
    )
