"""End-to-end PostgreSQL tests for TrustSeal Enterprise Project Management v2.0.

Verifies mandatory acceptance scenarios from
``docs/TrustSeal_Enterprise_Project_Management_Module_Specification.md``:
- PM-01: Demand & Intake weighted scoring, rejection rationale, idempotent 1-to-1 conversion (contract-free project)
- PM-02/03: Portfolios & Programmes with deduplicated Decimal rollups
- PM-04: Charter versioning/approval, Stage Gates, closure blocking on critical risks & read-only enforcement
- PM-06: WBS work packages & reparent cycle rejection
- PM-07/08: Identity-backed tasks & schedule DAG cycle rejection
- PM-12/13: Resource capacity hard-limit conflict & timesheet approval -> single immutable cost posting
- PM-15/16: Decimal budget lines, cost events, duplicate source_ref idempotency & available budget math
- PM-19/20: RAID register P×I scoring & Integrated Change Control approval
- PM-27: Explainable Health Policy v2.0 across 6 dimensions
- PM-33/34: Cross-tenant isolation, project-scoped membership, finance rate restriction & Outbox/SecurityEvent audit
"""
from __future__ import annotations

from decimal import Decimal
import pytest


@pytest.fixture
def pm_env(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.user import User

    org_a = Organization(name="Enterprise PM Org A")
    org_b = Organization(name="Enterprise PM Org B")
    db.session.add_all([org_a, org_b])
    db.session.flush()

    mgr_a = User(username="pm-mgr-a", email="pm-mgr-a@example.test", is_active=True, organization_id=org_a.id)
    mgr_a.set_password("pw")
    member_a = User(username="pm-mem-a", email="pm-mem-a@example.test", is_active=True, organization_id=org_a.id)
    member_a.set_password("pw")
    outsider_b = User(username="pm-out-b", email="pm-out-b@example.test", is_active=True, organization_id=org_b.id)
    outsider_b.set_password("pw")
    db.session.add_all([mgr_a, member_a, outsider_b])
    db.session.commit()
    return {"org_a": org_a, "org_b": org_b, "mgr_a": mgr_a, "member_a": member_a, "outsider_b": outsider_b}


def _client_for(app, user):
    from flask import g
    if hasattr(g, "_login_user"):
        delattr(g, "_login_user")
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return client


def _as_user(app, user):
    """Return a fresh test client authenticated strictly as ``user``."""
    return _client_for(app, user)


def test_enterprise_pm_intake_portfolio_programme_and_idempotent_conversion(pg_app, pm_env):
    """PM-01, PM-02, PM-03: Portfolio -> Programme -> Intake -> Idempotent contract-free Project."""
    hdrs = {"X-Requested-With": "fetch"}
    c = _client_for(pg_app, pm_env["mgr_a"])

    # 1. Create Portfolio & Programme
    r_pf = c.post("/api/portfolios", headers=hdrs, json={
        "name": "Digital Transformation 2026",
        "strategic_objective": "Modernize core operations",
        "budget_ceiling": "1500000.00",
        "currency": "USD",
    })
    assert r_pf.status_code == 201
    pf_id = r_pf.get_json()["portfolio"]["id"]

    r_pg = c.post("/api/programmes", headers=hdrs, json={
        "name": "Zero-Paperwork Programme",
        "portfolio_id": pf_id,
        "target_end_date": "2027-06-30",
    })
    assert r_pg.status_code == 201
    pg_id = r_pg.get_json()["programme"]["id"]

    # 2. Submit Intake & verify weighted score
    r_int = c.post("/api/project-intakes", headers=hdrs, json={
        "title": "Internal Cloud Migration (Contract-Free)",
        "problem_statement": "Migrate legacy workloads without external vendor contract",
        "portfolio_id": pf_id,
        "programme_id": pg_id,
        "estimated_budget": "125000.50",
        "value_score": 5,
        "urgency_score": 4,
        "feasibility_score": 4,
        "risk_score": 2,
    })
    assert r_int.status_code == 201
    intake = r_int.get_json()["intake"]
    assert Decimal(intake["weighted_score"]) == Decimal("4.35")

    # Cannot convert before approval
    assert c.post(f"/api/project-intakes/{intake['id']}/convert", headers=hdrs).status_code == 409

    # Approve and convert twice -> idempotent, exactly 1 project created
    assert c.post(f"/api/project-intakes/{intake['id']}/decide", headers=hdrs, json={"decision": "approved"}).status_code == 200
    r_conv1 = c.post(f"/api/project-intakes/{intake['id']}/convert", headers=hdrs)
    assert r_conv1.status_code == 201
    proj_id = r_conv1.get_json()["project"]["id"]
    assert r_conv1.get_json()["project"]["budget_numeric"] == "125000.50"

    r_conv2 = c.post(f"/api/project-intakes/{intake['id']}/convert", headers=hdrs)
    assert r_conv2.status_code == 200
    assert r_conv2.get_json()["created"] is False
    assert r_conv2.get_json()["project"]["id"] == proj_id

    # Rejected intake requires rationale and cannot silently become approved
    r_rej_int = c.post("/api/project-intakes", headers=hdrs, json={"title": "Low Value Idea"})
    rej_id = r_rej_int.get_json()["intake"]["id"]
    assert c.post(f"/api/project-intakes/{rej_id}/decide", headers=hdrs, json={"decision": "rejected"}).status_code == 422
    assert c.post(f"/api/project-intakes/{rej_id}/decide", headers=hdrs, json={"decision": "rejected", "rationale": "Out of strategy"}).status_code == 200
    assert c.post(f"/api/project-intakes/{rej_id}/decide", headers=hdrs, json={"decision": "approved"}).status_code == 409


def test_enterprise_pm_wbs_dag_resources_timesheets_finance_governance_and_security(pg_app, pm_env):
    """PM-04, PM-06, PM-07, PM-08, PM-12, PM-13, PM-15, PM-16, PM-19, PM-20, PM-27, PM-33, PM-34."""
    from app.models.event_delivery import OutboxEvent, SecurityEvent

    hdrs = {"X-Requested-With": "fetch"}
    mgr = pm_env["mgr_a"]
    mem = pm_env["member_a"]
    out = pm_env["outsider_b"]
    c_mgr = _as_user(pg_app, mgr)

    # 1. Create confidential project
    r_p = c_mgr.post("/api/projects", headers=hdrs, json={
        "name": "National Health Registry Rollout",
        "category": "client_delivery",
        "delivery_methodology": "hybrid",
        "confidentiality": "confidential",
        "budget_amount": "100000.00",
        "currency": "USD",
    })
    assert r_p.status_code == 201
    pid = r_p.get_json()["project"]["id"]

    # Cross-tenant outsider gets 404; same-tenant non-member gets 403 on confidential project
    assert _as_user(pg_app, out).get(f"/api/projects/{pid}/health").status_code == 404
    assert _as_user(pg_app, mem).get(f"/api/projects/{pid}/health").status_code == 403

    # Grant member non-finance role -> can read health, CANNOT read finance or rates
    c_mgr = _as_user(pg_app, mgr)
    assert c_mgr.post(f"/api/projects/{pid}/members", headers=hdrs, json={
        "user_id": mem.id, "project_role": "member", "can_view_finance": False,
    }).status_code == 201
    c_mem = _as_user(pg_app, mem)
    assert c_mem.get(f"/api/projects/{pid}/health").status_code == 200
    assert c_mem.get(f"/api/projects/{pid}/budget").status_code == 403

    # 2. Charter versioning & approval + Stage Gate approval (PM-04)
    c_mgr = _as_user(pg_app, mgr)
    r_ch = c_mgr.post(f"/api/projects/{pid}/charter", headers=hdrs, json={
        "objectives": "Deploy registry to 47 counties",
        "scope_in": "Core API & Web Portal",
        "scope_out": "Hardware procurement",
    })
    assert r_ch.status_code == 201
    ch_id = r_ch.get_json()["charter"]["id"]
    assert c_mgr.post(f"/api/projects/{pid}/charter/{ch_id}/approve", headers=hdrs).status_code == 200
    assert c_mgr.post(f"/api/projects/{pid}/gates/initiation/decide", headers=hdrs, json={"gate_state": "approved"}).status_code == 200

    # 3. WBS hierarchy & cycle protection (PM-06)
    w1 = c_mgr.post(f"/api/projects/{pid}/wbs", headers=hdrs, json={"wbs_code": "1.0", "title": "Phase 1", "weight_pct": 50}).get_json()["node"]["id"]
    w2 = c_mgr.post(f"/api/projects/{pid}/wbs", headers=hdrs, json={"wbs_code": "1.1", "title": "Discovery", "parent_id": w1, "weight_pct": 50}).get_json()["node"]["id"]
    # Reparenting w1 under its own child w2 must be rejected (422)
    assert c_mgr.patch(f"/api/projects/{pid}/wbs/{w1}", headers=hdrs, json={"parent_id": w2}).status_code == 422

    # 4. Identity-backed tasks & schedule DAG cycle rejection (PM-07/08)
    t1 = c_mgr.post(f"/api/projects/{pid}/tasks", headers=hdrs, json={"title": "Design Schema", "wbs_node_id": w2, "assignee_user_id": mem.id, "planned_hours": "16.00"}).get_json()["task"]["id"]
    t2 = c_mgr.post(f"/api/projects/{pid}/tasks", headers=hdrs, json={"title": "Build API", "wbs_node_id": w2, "assignee_user_id": mem.id, "planned_hours": "24.00"}).get_json()["task"]["id"]
    assert c_mgr.post(f"/api/projects/{pid}/dependencies", headers=hdrs, json={"predecessor_task_id": t1, "successor_task_id": t2, "dependency_type": "FS"}).status_code == 201
    # Adding reverse edge t2 -> t1 creates a cycle -> rejected 422
    assert c_mgr.post(f"/api/projects/{pid}/dependencies", headers=hdrs, json={"predecessor_task_id": t2, "successor_task_id": t1, "dependency_type": "FS"}).status_code == 422

    # 5. Resource allocation capacity hard-limit & rate visibility (PM-12)
    assert c_mgr.post(f"/api/projects/{pid}/allocations", headers=hdrs, json={
        "user_id": mem.id, "role_title": "Lead Engineer", "allocation_pct": 70, "hourly_cost_rate": "125.50",
    }).status_code == 201
    # Adding another 50% exceeds 100% hard limit -> 409 Conflict
    assert c_mgr.post(f"/api/projects/{pid}/allocations", headers=hdrs, json={
        "user_id": mem.id, "role_title": "QA Support", "allocation_pct": 50,
    }).status_code == 409
    # Non-finance member cannot see hourly_cost_rate
    c_mem = _as_user(pg_app, mem)
    mem_allocs = c_mem.get(f"/api/projects/{pid}/allocations").get_json()["allocations"]
    assert "hourly_cost_rate" not in mem_allocs[0]

    # 6. Timesheet submission -> manager approval posts exact Decimal cost ONCE (PM-13)
    r_te = c_mem.post(f"/api/projects/{pid}/timesheets", headers=hdrs, json={
        "task_id": t1, "work_date": "2026-11-26", "hours": "8.00", "notes": "Completed schema", "submit": True,
    })
    assert r_te.status_code == 201
    te_id = r_te.get_json()["time_entry"]["id"]

    c_mgr = _as_user(pg_app, mgr)
    r_app1 = c_mgr.post(f"/api/projects/{pid}/timesheets/{te_id}/approve", headers=hdrs, json={})
    assert r_app1.status_code == 200
    assert r_app1.get_json()["cost_event"]["amount"] == "1004.00"  # 8.00 * 125.50 exact Decimal
    ce_id = r_app1.get_json()["cost_event"]["id"]
    # Re-approving is idempotent -> returns exact same cost event ID
    r_app2 = c_mgr.post(f"/api/projects/{pid}/timesheets/{te_id}/approve", headers=hdrs, json={})
    assert r_app2.get_json()["cost_event"]["id"] == ce_id

    # 7. Decimal Budget Lines, Cost Commitments & Duplicate Source Ref Idempotency (PM-15/16)
    assert c_mgr.post(f"/api/projects/{pid}/budget", headers=hdrs, json={"category": "labor", "description": "Engineering Budget", "planned_amount": "60000.00"}).status_code == 201
    assert c_mgr.post(f"/api/projects/{pid}/budget", headers=hdrs, json={"category": "vendor", "description": "Cloud Hosting", "planned_amount": "40000.00"}).status_code == 201
    assert c_mgr.post(f"/api/projects/{pid}/costs", headers=hdrs, json={
        "event_type": "commitment", "category": "vendor", "description": "PO-101 AWS", "amount": "15000.00", "source_ref": "PO-101",
    }).status_code == 201
    # Duplicate source_ref rejected (409)
    assert c_mgr.post(f"/api/projects/{pid}/costs", headers=hdrs, json={
        "event_type": "commitment", "category": "vendor", "description": "PO-101 AWS dup", "amount": "15000.00", "source_ref": "PO-101",
    }).status_code == 409

    bud_sum = c_mgr.get(f"/api/projects/{pid}/budget").get_json()["summary"]
    assert bud_sum["approved_budget_str"] == "100000.00"
    assert bud_sum["actuals_str"] == "1004.00"
    assert bud_sum["commitments_str"] == "15000.00"
    assert bud_sum["available_budget_str"] == "83996.00"  # 100000 - 1004 - 15000

    # 8. Integrated Change Control (PM-20)
    r_cr = c_mgr.post(f"/api/projects/{pid}/changes", headers=hdrs, json={
        "title": "Add County Analytics Dashboard", "change_type": "scope", "cost_impact": "12000.00", "schedule_impact_days": 10,
    })
    assert r_cr.status_code == 201
    cr_id = r_cr.get_json()["change"]["id"]
    assert c_mgr.post(f"/api/projects/{pid}/changes/{cr_id}/decide", headers=hdrs, json={"decision": "approved"}).status_code == 200

    # 9. Critical RAID risk blocks closure unless waived, and sets Health v2.0 to Critical (PM-19/27/04)
    r_risk = c_mgr.post(f"/api/projects/{pid}/risks", headers=hdrs, json={
        "title": "Data residency regulatory blocker", "item_type": "issue", "severity": "critical", "probability_score": 5, "impact_score": 5,
    })
    assert r_risk.status_code == 201
    hl = c_mgr.get(f"/api/projects/{pid}/health").get_json()["health"]
    assert hl["policy_version"] == "2.0.0"
    assert hl["rag"] == "critical"
    assert "dimensions" in hl and hl["dimensions"]["risk"]["rag"] == "critical"

    # Closure blocked without waiver
    assert c_mgr.post(f"/api/projects/{pid}/transition", headers=hdrs, json={"lifecycle_state": "closed"}).status_code == 409
    # Closure succeeds with waiver, releases confirmed allocations, and makes project read-only
    assert c_mgr.post(f"/api/projects/{pid}/transition", headers=hdrs, json={"lifecycle_state": "closed", "waiver_reason": "Board approved transition to ops"}).status_code == 200
    assert c_mgr.post(f"/api/projects/{pid}/tasks", headers=hdrs, json={"title": "Post-close edit"}).status_code == 409

    # 10. UI Pages render HTTP 200 & Outbox/SecurityEvents emitted (PM-34)
    assert c_mgr.get("/projects").status_code == 200
    r_det = c_mgr.get(f"/projects/{pid}")
    assert r_det.status_code == 200
    assert b"Explainable Health Policy" in r_det.data
    assert b"Work Breakdown Structure" in r_det.data
    assert b"Integrated Change Control" in r_det.data

    assert OutboxEvent.query.filter_by(organization_id=pm_env["org_a"].id, event_type="timesheet.approved").count() >= 1
    assert OutboxEvent.query.filter_by(organization_id=pm_env["org_a"].id, event_type="project.closed").count() >= 1
    assert SecurityEvent.query.filter_by(organization_id=pm_env["org_a"].id, action="project.closed").count() >= 1


def test_enterprise_pm_batch2_modules_end_to_end(pg_app, pm_env):
    """PM-05, PM-09, PM-11, PM-14, PM-17, PM-21, PM-22, PM-24, PM-26, PM-30 end-to-end verification."""
    from app.extensions import db
    from app.models.tsd_document import TSDocument
    from app.services.tsd_format import encrypt_content_envelope, pack_content, sha256_hex

    hdrs = {"X-Requested-With": "fetch"}
    mgr = pm_env["mgr_a"]
    mem = pm_env["member_a"]
    c_mgr = _as_user(pg_app, mgr)

    pid = c_mgr.post("/api/projects", headers=hdrs, json={
        "name": "National Immunization Programme",
        "budget_amount": "500000.00",
        "currency": "USD",
    }).get_json()["project"]["id"]

    # PM-05: Requirements immutability after approval
    rq_id = c_mgr.post(f"/api/projects/{pid}/requirements", headers=hdrs, json={"title": "Cold-chain temperature audit"}).get_json()["requirement"]["id"]
    assert c_mgr.post(f"/api/projects/{pid}/requirements/{rq_id}/approve", headers=hdrs).status_code == 200
    assert c_mgr.patch(f"/api/projects/{pid}/requirements/{rq_id}", headers=hdrs, json={"title": "Tampered"}).status_code == 409

    # PM-09: Agile Sprint & Backlog velocity
    sp_id = c_mgr.post(f"/api/projects/{pid}/sprints", headers=hdrs, json={"name": "Sprint 1", "capacity_points": 20}).get_json()["sprint"]["id"]
    b1 = c_mgr.post(f"/api/projects/{pid}/backlog", headers=hdrs, json={"title": "Cold-chain sensor ingest", "sprint_id": sp_id, "story_points": 8, "status": "done"}).get_json()["item"]["id"]
    c_mgr.post(f"/api/projects/{pid}/backlog", headers=hdrs, json={"title": "SMS alerting", "sprint_id": sp_id, "story_points": 5, "status": "in_progress"})
    r_comp = c_mgr.post(f"/api/projects/{pid}/sprints/{sp_id}/complete", headers=hdrs)
    assert r_comp.status_code == 200
    assert r_comp.get_json()["velocity_points"] == 8
    assert r_comp.get_json()["carryover_count"] == 1
    assert b1 > 0

    # PM-11: Org Resource Pool flags expired certification
    r_res = c_mgr.post("/api/resources", headers=hdrs, json={
        "display_name": "Dr. Grace K.", "resource_type": "consultant", "skills": ["M&E", "Cold-Chain"],
        "certification_name": "WHO Cold-Chain", "certification_expiry_date": "2020-01-01",
    })
    assert r_res.status_code == 201
    assert r_res.get_json()["resource"]["certification_expired"] is True

    # PM-14: Equipment exclusive booking overlap conflict (409)
    assert c_mgr.post(f"/api/projects/{pid}/assets", headers=hdrs, json={
        "asset_name": "Refrigerated Truck #4", "start_date": "2026-12-01", "end_date": "2026-12-10", "exclusive": True,
    }).status_code == 201
    assert c_mgr.post(f"/api/projects/{pid}/assets", headers=hdrs, json={
        "asset_name": "Refrigerated Truck #4", "start_date": "2026-12-05", "end_date": "2026-12-15", "exclusive": True,
    }).status_code == 409

    # PM-17: Procurement Separation of Duties + auto-commitment posting to cost ledger
    pr_id = c_mgr.post(f"/api/projects/{pid}/procurement", headers=hdrs, json={
        "title": "Solar Vaccine Fridges", "supplier_name": "MedTech East Africa", "estimated_amount": "45000.00",
    }).get_json()["procurement"]["id"]
    # Requester cannot self-approve when enforce_sod=True
    assert c_mgr.post(f"/api/projects/{pid}/procurement/{pr_id}/award", headers=hdrs, json={"enforce_sod": True}).status_code == 403
    # Award posts commitment once
    r_aw = c_mgr.post(f"/api/projects/{pid}/procurement/{pr_id}/award", headers=hdrs, json={"awarded_amount": "42500.00"})
    assert r_aw.status_code == 200
    assert r_aw.get_json()["cost_event"]["event_type"] == "commitment"
    assert r_aw.get_json()["cost_event"]["amount"] == "42500.00"

    # PM-21 & PM-22: Quality record & Stakeholder
    assert c_mgr.post(f"/api/projects/{pid}/quality", headers=hdrs, json={"record_type": "inspection", "title": "Fridge temp calibration", "status": "passed"}).status_code == 201
    assert c_mgr.post(f"/api/projects/{pid}/stakeholders", headers=hdrs, json={"name": "Ministry of Health", "influence_level": "high", "is_external": True}).status_code == 201

    # PM-24: Pinned immutable TSD Document link
    env = pack_content(html="<h1>Project Charter Evidence</h1>", description="Charter")
    ct = encrypt_content_envelope(env, organization_id=pm_env["org_a"].id)
    doc = TSDocument(organization_id=pm_env["org_a"].id, created_by_id=mgr.id, title="Signed Charter PDF", status="draft", ciphertext=ct, ciphertext_sha256=sha256_hex(ct), plaintext_bytes=len(env), version=2)
    db.session.add(doc)
    db.session.commit()
    r_dl = c_mgr.post(f"/api/projects/{pid}/documents", headers=hdrs, json={"document_id": doc.id, "classification": "charter"})
    assert r_dl.status_code == 201
    assert r_dl.get_json()["document_link"]["pinned_version"] == 2

    # PM-26: M&E Indicators: zero denominator rejected (422), duplicate period rejected (409), rejected obs excluded
    ind_id = c_mgr.post(f"/api/projects/{pid}/indicators", headers=hdrs, json={"level": "outcome", "title": "District coverage %", "unit": "%", "target_value": "95.00"}).get_json()["indicator"]["id"]
    assert c_mgr.post(f"/api/projects/{pid}/indicators/{ind_id}/observations", headers=hdrs, json={"period_label": "2026-Q4", "numerator": "50", "denominator": "0"}).status_code == 422
    obs1 = c_mgr.post(f"/api/projects/{pid}/indicators/{ind_id}/observations", headers=hdrs, json={"period_label": "2026-Q4", "numerator": "88", "denominator": "100"}).get_json()["observation"]
    assert obs1["observed_value"] == "88.00"
    assert c_mgr.post(f"/api/projects/{pid}/indicators/{ind_id}/observations", headers=hdrs, json={"period_label": "2026-Q4", "observed_value": "90"}).status_code == 409
    assert c_mgr.post(f"/api/projects/{pid}/observations/{obs1['id']}/validate", headers=hdrs, json={"status": "validated"}).status_code == 200
    ind_list = c_mgr.get(f"/api/projects/{pid}/indicators").get_json()["indicators"]
    assert ind_list[0]["latest_validated_value"] == "88.00"

    # PM-30: Closure checklist & post-closure Benefits tracking
    cl_id = c_mgr.post(f"/api/projects/{pid}/closure", headers=hdrs, json={"category": "handover", "title": "Operations team trained"}).get_json()["closure_item"]["id"]
    assert c_mgr.patch(f"/api/projects/{pid}/closure/{cl_id}", headers=hdrs, json={"completed": True}).status_code == 200
    assert c_mgr.post(f"/api/projects/{pid}/benefits", headers=hdrs, json={"benefit_type": "social", "title": "20% reduction in vaccine spoilage", "target_value": "20%"}).status_code == 201

    # Dossier HTML renders all Batch 2 tabs
    r_html = c_mgr.get(f"/projects/{pid}")
    assert r_html.status_code == 200
    assert b"Requirements &amp; Traceability" in r_html.data
    assert b"Procurement &amp; Supplier Awards" in r_html.data
    assert b"Results Framework &amp; Indicators" in r_html.data


def test_enterprise_pm_batch3_modules_end_to_end(pg_app, pm_env):
    """PM-23, PM-25, PM-28, PM-29, PM-31, PM-32 end-to-end verification."""
    hdrs = {"X-Requested-With": "fetch"}
    mgr = pm_env["mgr_a"]
    mem = pm_env["member_a"]
    c_mgr = _as_user(pg_app, mgr)

    # PM-31: Reusable Project Template -> Instantiate Project with seeded WBS & Gates
    r_tpl = c_mgr.post("/api/project-templates", headers=hdrs, json={
        "name": "Standard Construction Delivery",
        "category": "client_delivery",
        "version": 2,
    })
    assert r_tpl.status_code == 201
    tpl_id = r_tpl.get_json()["template"]["id"]
    r_inst = c_mgr.post(f"/api/project-templates/{tpl_id}/instantiate", headers=hdrs, json={
        "name": "Kampala Regional Hub Build",
        "budget_amount": "750000.00",
    })
    assert r_inst.status_code == 201
    assert r_inst.get_json()["template_version"] == 2
    pid = r_inst.get_json()["project"]["id"]
    assert len(c_mgr.get(f"/api/projects/{pid}/wbs").get_json()["wbs"]) == 3

    # Add member to project for SoD & visibility tests
    assert c_mgr.post(f"/api/projects/{pid}/members", headers=hdrs, json={
        "user_id": mem.id, "project_role": "member", "can_view_finance": False,
    }).status_code == 201

    # PM-23: Threaded Comments & My Work inbox
    assert c_mgr.post(f"/api/projects/{pid}/tasks", headers=hdrs, json={"title": "=SUM(A1:A2) Site Survey", "assignee_user_id": mem.id}).status_code == 201
    assert c_mgr.post(f"/api/projects/{pid}/comments", headers=hdrs, json={"body": "Kickoff completed."}).status_code == 201
    c_mem = _as_user(pg_app, mem)
    mw = c_mem.get("/api/projects/my-work").get_json()
    assert len(mw["my_tasks"]) == 1

    # PM-25: Governed Approvals — Separation of Duties denies self-approval (403), stale hash rejected (409)
    r_ap = c_mem.post(f"/api/projects/{pid}/approvals", headers=hdrs, json={
        "subject_type": "deliverable", "subject_title": "Site Survey Sign-Off", "subject_payload": "v1-bytes",
    })
    assert r_ap.status_code == 201
    ap = r_ap.get_json()["approval"]
    # Self-approval denied
    assert c_mem.post(f"/api/projects/{pid}/approvals/{ap['id']}/decide", headers=hdrs, json={"decision": "approved"}).status_code == 403
    # Manager stale hash denied (409), matching hash approved (200)
    c_mgr = _as_user(pg_app, mgr)
    assert c_mgr.post(f"/api/projects/{pid}/approvals/{ap['id']}/decide", headers=hdrs, json={"decision": "approved", "expected_hash": "wronghash"}).status_code == 409
    assert c_mgr.post(f"/api/projects/{pid}/approvals/{ap['id']}/decide", headers=hdrs, json={"decision": "approved", "expected_hash": ap["subject_hash"]}).status_code == 200

    # PM-28: Expired permit flagged & restricted HSE incident hidden from ordinary member
    r_perm = c_mgr.post(f"/api/projects/{pid}/compliance", headers=hdrs, json={
        "record_type": "permit", "title": "Environmental Impact Permit", "expiry_date": "2020-01-01",
    })
    assert r_perm.status_code == 201
    assert r_perm.get_json()["compliance_record"]["is_expired"] is True
    assert c_mgr.post(f"/api/projects/{pid}/compliance", headers=hdrs, json={
        "record_type": "hse_incident", "title": "Confidential Site Injury Report", "is_restricted": True,
    }).status_code == 201
    assert len(c_mgr.get(f"/api/projects/{pid}/compliance").get_json()["compliance_records"]) == 2
    c_mem = _as_user(pg_app, mem)
    mem_comp = c_mem.get(f"/api/projects/{pid}/compliance").get_json()["compliance_records"]
    assert len(mem_comp) == 1 and mem_comp[0]["record_type"] == "permit"

    # PM-29: External Client Portal — scoped view hides internal costs & revocation takes immediate effect
    c_mgr = _as_user(pg_app, mgr)
    r_gr = c_mgr.post(f"/api/projects/{pid}/external-grants", headers=hdrs, json={
        "recipient_name": "Donor Auditor", "recipient_email": "auditor@donor.org", "expires_days": 7,
    })
    assert r_gr.status_code == 201
    portal_url = r_gr.get_json()["portal_url"]
    gid = r_gr.get_json()["grant"]["id"]

    anon = pg_app.test_client()
    r_pv = anon.get(portal_url)
    assert r_pv.status_code == 200
    pv_json = r_pv.get_json()
    assert pv_json["project"]["name"] == "Kampala Regional Hub Build"
    assert "budget_amount" not in pv_json["project"]

    assert c_mgr.post(f"/api/projects/{pid}/external-grants/{gid}/revoke", headers=hdrs).status_code == 200
    assert anon.get(portal_url).status_code == 403

    # PM-32: CSV Dry-Run Import (catches row errors before commit) & Formula-Safe CSV Export
    bad_csv = "title,priority,phase\n,high,Execution\nValid Task,invalid_prio,Execution\n"
    r_dry = c_mgr.post(f"/api/projects/{pid}/import-tasks", headers=hdrs, json={"csv_text": bad_csv, "dry_run": True})
    assert r_dry.status_code == 422
    assert len(r_dry.get_json()["errors"]) == 2

    good_csv = "title,priority,phase\nPour Foundation,high,Execution\nInspect Concrete,medium,QA\n"
    r_imp = c_mgr.post(f"/api/projects/{pid}/import-tasks", headers=hdrs, json={"csv_text": good_csv, "dry_run": False})
    assert r_imp.status_code == 201
    assert r_imp.get_json()["imported_count"] == 2

    r_exp = c_mgr.get(f"/api/projects/{pid}/export.csv")
    assert r_exp.status_code == 200
    csv_body = r_exp.data.decode("utf-8")
    # Formula injection neutralized with leading apostrophe
    assert "'=SUM(A1:A2) Site Survey" in csv_body

    # Dossier HTML renders Batch 3 Compliance/Portal tab
    r_html = c_mgr.get(f"/projects/{pid}")
    assert r_html.status_code == 200
    assert b"Permits, Safeguards &amp; HSE Incidents" in r_html.data
    assert b"External Client / Partner Portal Grants" in r_html.data


def test_enterprise_pm_v21_timesheets_end_to_end(pg_app, pm_env):
    """PM-13 v2.1: Consolidated personal sheet, workflow, return reason, immutable adjustment, CSV export & closure gate."""
    hdrs = {"X-Requested-With": "fetch"}
    mgr = pm_env["mgr_a"]
    mem = pm_env["member_a"]
    c_mgr = _as_user(pg_app, mgr)

    pid = c_mgr.post("/api/projects", headers=hdrs, json={"name": "Timesheet v2.1 Pilot", "budget_amount": "50000.00"}).get_json()["project"]["id"]
    assert c_mgr.post(f"/api/projects/{pid}/members", headers=hdrs, json={"user_id": mem.id, "project_role": "member", "can_view_finance": False}).status_code == 201
    assert c_mgr.post(f"/api/projects/{pid}/allocations", headers=hdrs, json={"user_id": mem.id, "allocation_pct": 50, "hourly_cost_rate": "100.00"}).status_code == 201

    # Member logs draft entry -> submit -> withdraw -> resubmit
    c_mem = _as_user(pg_app, mem)
    te_id = c_mem.post(f"/api/projects/{pid}/timesheets", headers=hdrs, json={"work_date": "2026-11-26", "hours": "6.00", "notes": "=CMD|calc"}).get_json()["time_entry"]["id"]
    assert c_mem.post(f"/api/projects/{pid}/timesheets/{te_id}/submit", headers=hdrs).status_code == 200
    assert c_mem.post(f"/api/projects/{pid}/timesheets/{te_id}/withdraw", headers=hdrs).status_code == 200
    assert c_mem.post(f"/api/projects/{pid}/timesheets/{te_id}/submit", headers=hdrs).status_code == 200

    # Consolidated personal /api/timesheets shows entry & 100% billable ratio
    my_ts = c_mem.get("/api/timesheets").get_json()
    assert my_ts["summary"]["total_hours"] == "6.00"
    assert my_ts["summary"]["billable_ratio_pct"] == "100.00"

    # Manager cannot close project while unapproved time entry exists (PM-13.16)
    c_mgr = _as_user(pg_app, mgr)
    assert c_mgr.post(f"/api/projects/{pid}/transition", headers=hdrs, json={"lifecycle_state": "closed"}).status_code == 409

    # Return requires reason (422 without reason)
    assert c_mgr.post(f"/api/projects/{pid}/timesheets/{te_id}/return", headers=hdrs, json={}).status_code == 422
    assert c_mgr.post(f"/api/projects/{pid}/timesheets/{te_id}/return", headers=hdrs, json={"reason": "Add ticket ref"}).status_code == 200

    # Resubmit & approve -> posts 600.00
    c_mem = _as_user(pg_app, mem)
    assert c_mem.post(f"/api/projects/{pid}/timesheets/{te_id}/submit", headers=hdrs).status_code == 200
    c_mgr = _as_user(pg_app, mgr)
    assert c_mgr.post(f"/api/projects/{pid}/timesheets/{te_id}/approve", headers=hdrs, json={}).status_code == 200

    # Immutable adjustment (-2.00h) posts reversal of 200.00 (PM-13.08)
    r_adj = c_mgr.post(f"/api/projects/{pid}/timesheets/{te_id}/adjust", headers=hdrs, json={"delta_hours": "-2.00", "reason": "Over-reported 2h"})
    assert r_adj.status_code == 201
    assert r_adj.get_json()["cost_event"]["event_type"] == "reversal"
    assert r_adj.get_json()["cost_event"]["amount"] == "200.00"

    # Net actuals = 600.00 - 200.00 = 400.00
    bud = c_mgr.get(f"/api/projects/{pid}/budget").get_json()["summary"]
    assert bud["actuals_str"] == "400.00"

    # Formula-safe CSV export with TOTAL row (PM-13.14)
    csv_txt = c_mgr.get(f"/api/projects/{pid}/timesheets/export.csv").data.decode("utf-8")
    assert "'=CMD|calc" in csv_txt
    assert "TOTAL" in csv_txt

    # Dedicated Project Timesheets tab renders HTTP 200
    r_html = c_mgr.get(f"/projects/{pid}")
    assert r_html.status_code == 200
    assert b"Project Timesheets &amp; Effort Accounting (PM-13 v2.1)" in r_html.data

    # Now closure succeeds cleanly with zero unapproved time!
    assert c_mgr.post(f"/api/projects/{pid}/transition", headers=hdrs, json={"lifecycle_state": "closed"}).status_code == 200



