"""End-to-end tests for the enhanced TrustSeal Contracts Lifecycle Management module."""
from __future__ import annotations

import zipfile
import io

import pytest


@pytest.fixture
def contract_env(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.tsd_document import TSDocument
    from app.models.user import User
    from app.services.tsd_format import encrypt_content_envelope, pack_content, sha256_hex

    org_a = Organization(name="Contracts Org A")
    org_b = Organization(name="Contracts Org B")
    db.session.add_all([org_a, org_b])
    db.session.flush()

    user_a = User(
        username="clm-user-a",
        email="clm-a@example.test",
        is_active=True,
        organization_id=org_a.id,
    )
    user_a.set_password("pw")
    user_b = User(
        username="clm-user-b",
        email="clm-b@example.test",
        is_active=True,
        organization_id=org_b.id,
    )
    user_b.set_password("pw")
    db.session.add_all([user_a, user_b])
    db.session.flush()

    env = pack_content(html="<h1>Master Service Agreement</h1><p>Initial draft clause.</p>", description="Acme MSA")
    ct = encrypt_content_envelope(env, organization_id=org_a.id)
    pt = len(env)
    doc = TSDocument(
        organization_id=org_a.id,
        created_by_id=user_a.id,
        title="Acme MSA",
        status="draft",
        ciphertext=ct,
        ciphertext_sha256=sha256_hex(ct),
        plaintext_bytes=pt,
        version=1,
    )
    db.session.add(doc)
    db.session.commit()
    return {"org_a": org_a, "org_b": org_b, "user_a": user_a, "user_b": user_b, "doc": doc}


def _client_for(app, user):
    from flask import g
    if hasattr(g, "_login_user"):
        delattr(g, "_login_user")
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return client


def test_contract_cross_tenant_isolation(pg_app, contract_env):
    user_b = contract_env["user_b"]
    doc = contract_env["doc"]
    with pg_app.test_client() as client_b:
        with client_b.session_transaction() as sess:
            sess["_user_id"] = str(user_b.id)
            sess["_fresh"] = True
        assert client_b.get(f"/api/contracts/{doc.id}/state").status_code == 404
        assert client_b.get(f"/contracts/{doc.id}/workflow").status_code == 404


def test_full_contract_lifecycle_end_to_end(pg_app, contract_env):
    from app.extensions import db
    from app.models.event_delivery import OutboxEvent, SecurityEvent
    from app.models.evidence_preservation import EvidenceLegalHold, EvidenceRetention

    user_a = contract_env["user_a"]
    doc = contract_env["doc"]

    client_a = _client_for(pg_app, user_a)

    # 2. Portfolio & unified workspace pages render
    r_port = client_a.get("/contracts")
    assert r_port.status_code == 200
    assert b"Total Contracts" in r_port.data

    r_ws = client_a.get(f"/contracts/{doc.id}/workflow")
    assert r_ws.status_code == 200
    assert b"ts-ed__ribbon" in r_ws.data
    assert b"Contract &amp; Deliverables" in r_ws.data
    assert b"Sign &amp; Seal" in r_ws.data
    assert b"cw-stepper" not in r_ws.data

    # 3. Hydrate state, edit content, and verify version diff
    r_st = client_a.get(f"/api/contracts/{doc.id}/state")
    assert r_st.status_code == 200
    st = r_st.get_json()
    assert st["doc"]["version"] == 1
    assert "Initial draft clause" in st["doc"]["html"]

    hdrs = {"X-Requested-With": "fetch"}

    r_save = client_a.post(
        f"/api/contracts/{doc.id}/content",
        headers=hdrs,
        json={"html": "<h1>Master Service Agreement</h1><p>Initial draft clause.</p><h2>2. Fees</h2><p>Net 30 days.</p>"},
    )
    assert r_save.status_code == 200
    assert r_save.get_json()["version"] == 2

    r_diff = client_a.get(f"/api/contracts/{doc.id}/diff?from=1&to=2")
    assert r_diff.status_code == 200
    diff = r_diff.get_json()["diff"]
    assert diff["added"] >= 1

    # 4. Stage transition to approval locks editing
    r_stg = client_a.post(f"/api/contracts/{doc.id}/stage", headers=hdrs, json={"stage": "approval", "note": "Legal OK"})
    assert r_stg.status_code == 200
    assert r_stg.get_json()["workflow"]["edit_locked"] is True

    r_locked = client_a.post(f"/api/contracts/{doc.id}/content", headers=hdrs, json={"html": "<p>Sneaky edit</p>"})
    assert r_locked.status_code == 409

    # 5. Sequential signing routing enforcement
    client_a.post(f"/api/contracts/{doc.id}/meta", headers=hdrs, json={"routing_mode": "sequential", "counterparty_name": "Acme Corp"})
    r_add = client_a.post(
        f"/api/contracts/{doc.id}/signers",
        headers=hdrs,
        json={"action": "add", "name": "Jane Counterparty", "email": "jane@acme.test", "role": "Counterparty Signatory"},
    )
    assert r_add.status_code == 200
    signers = r_add.get_json()["workflow"]["signers"]
    assert len(signers) == 2

    # Second signer cannot sign before first in sequential mode
    r_ooo = client_a.post(f"/api/contracts/{doc.id}/sign", headers=hdrs, json={"id": signers[1]["id"], "signature_text": "Jane"})
    assert r_ooo.status_code == 409

    # First signer signs, then second signs
    assert client_a.post(f"/api/contracts/{doc.id}/sign", headers=hdrs, json={"id": signers[0]["id"]}).status_code == 200
    assert client_a.post(f"/api/contracts/{doc.id}/sign", headers=hdrs, json={"id": signers[1]["id"]}).status_code == 200

    # 6. Atomic Deal Closing -> creates EvidenceRetention + SecurityEvent + OutboxEvent
    r_close = client_a.post(f"/api/contracts/{doc.id}/close", headers=hdrs, json={"note": "Fully executed"})
    assert r_close.status_code == 200
    closed = r_close.get_json()
    assert closed["status"] == "finalized"
    assert closed["evidence_retention_id"] is not None
    assert len(closed["execution_sha256"]) == 64

    ret = db.session.get(EvidenceRetention, closed["evidence_retention_id"])
    assert ret is not None
    assert ret.artifact_type in ("finalized_pdf", "stamped_pdf")

    assert SecurityEvent.query.filter_by(organization_id=user_a.organization_id, action="contract.closed").count() >= 1
    assert OutboxEvent.query.filter_by(organization_id=user_a.organization_id, event_type="contract.executed").count() >= 1

    # 7. Working PDF stream & Closing Binder ZIP
    r_pdf = client_a.get(f"/api/contracts/{doc.id}/pdf")
    assert r_pdf.status_code == 200
    assert r_pdf.data.startswith(b"%PDF-")

    r_zip = client_a.get(f"/api/contracts/{doc.id}/binder")
    assert r_zip.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r_zip.data)) as zf:
        names = set(zf.namelist())
        assert {"executed_contract.pdf", "contract_vault.tsd", "evidence_manifest.json"}.issubset(names)

    # 8. Legal hold blocks archival
    db.session.add(
        EvidenceLegalHold(
            retention_id=ret.id,
            organization_id=user_a.organization_id,
            reason="Litigation hold",
            requested_by_id=user_a.id,
        )
    )
    db.session.commit()
    r_arch = client_a.post(f"/api/contracts/{doc.id}/stage", headers=hdrs, json={"stage": "closed"})
    assert r_arch.status_code == 400
    assert "legal hold" in r_arch.get_json()["error"].lower()

    # 9. Post-execution: Obligations & Linked Amendment
    r_ob = client_a.post(
        f"/api/contracts/{doc.id}/obligations",
        headers=hdrs,
        json={"title": "Quarterly SLA Review", "category": "sla", "due_date": "2027-03-01"},
    )
    assert r_ob.status_code == 200
    ob_id = r_ob.get_json()["obligation"]["id"]
    assert client_a.patch(f"/api/contracts/{doc.id}/obligations/{ob_id}", headers=hdrs, json={"status": "completed"}).status_code == 200

    r_am = client_a.post(f"/api/contracts/{doc.id}/amendment", headers=hdrs, json={"relationship_type": "amendment"})
    assert r_am.status_code == 200
    assert r_am.get_json()["document_id"] != doc.id

    # 10. Termination
    r_term = client_a.post(f"/api/contracts/{doc.id}/terminate", headers=hdrs, json={"reason": "Mutual wind-down", "termination_type": "mutual"})
    assert r_term.status_code == 200
    assert r_term.get_json()["workflow"]["contract_status"] == "TERMINATED"


def test_projects_templates_statuses_probation_deliverables(pg_app, contract_env):
    """Verify Projects, Contract Templates, DRAFT/SIGNED/SUSPENDED/TERMINATED, Probation & Deliverables."""
    user_a = contract_env["user_a"]
    hdrs = {"X-Requested-With": "fetch"}
    client = _client_for(pg_app, user_a)

    # 1. Projects UI & API
    assert client.get("/projects").status_code == 200
    assert client.get("/contracts/templates").status_code == 200

    r_prj = client.post(
        "/api/projects",
        headers=hdrs,
        json={"name": "HR Q4 Engineering Onboarding", "category": "hr_onboarding", "budget_amount": 500000, "currency": "USD"},
    )
    assert r_prj.status_code == 201
    proj_id = r_prj.get_json()["project"]["id"]

    # 2. Templates API: locate seeded Employment (90-Day Probation) template and instantiate into Project
    r_tpls = client.get("/api/contract-templates?state=published")
    assert r_tpls.status_code == 200
    tpls = r_tpls.get_json()["templates"]
    prob_tpl = next(t for t in tpls if t["contract_type"] == "employment_probation")

    r_inst = client.post(
        f"/api/contract-templates/{prob_tpl['id']}/instantiate",
        headers=hdrs,
        json={
            "project_id": proj_id,
            "title": "Employment Agreement — Alice Dev",
            "variables": {
                "counterparty_name": "Alice Dev",
                "deal_value": "120,000",
                "effective_date": "2026-11-01",
                "probation_days": 90,
            },
        },
    )
    assert r_inst.status_code == 201
    doc_id = r_inst.get_json()["document_id"]

    # 3. Verify auto-seeded Probation Key Term & 3 Deliverables
    st = client.get(f"/api/contracts/{doc_id}/state").get_json()
    assert st["project"]["id"] == proj_id
    assert st["workflow"]["contract_status"] == "DRAFT"
    assert st["probation_term"] is not None
    assert len(st["deliverables"]) == 3

    # 4. Sign & Close (DRAFT -> SIGNED) activates deliverables
    r_close = client.post(f"/api/contracts/{doc_id}/close", headers=hdrs, json={"note": "Signed by HR & Alice"})
    assert r_close.status_code == 200
    assert r_close.get_json()["contract_status"] == "SIGNED"

    # 5. Suspend (SIGNED -> SUSPENDED) pauses active deliverables
    r_susp = client.post(f"/api/contracts/{doc_id}/suspend", headers=hdrs, json={"reason": "Unpaid medical leave"})
    assert r_susp.status_code == 200
    assert r_susp.get_json()["workflow"]["contract_status"] == "SUSPENDED"
    st_susp = client.get(f"/api/contracts/{doc_id}/state").get_json()
    assert all(d["status"] == "suspended" for d in st_susp["deliverables"])

    # 6. Resume (SUSPENDED -> SIGNED) resumes deliverables and shifts due dates
    r_res = client.post(f"/api/contracts/{doc_id}/resume", headers=hdrs, json={"note": "Returned to duty", "shift_due_dates_days": 14})
    assert r_res.status_code == 200
    assert r_res.get_json()["workflow"]["contract_status"] == "SIGNED"

    # 7. Accept first deliverable -> weighted progress > 0%
    first_dl_id = st_susp["deliverables"][0]["id"]
    assert client.patch(f"/api/contracts/{doc_id}/deliverables/{first_dl_id}", headers=hdrs, json={"status": "accepted"}).status_code == 200
    st_prog = client.get(f"/api/contracts/{doc_id}/state").get_json()
    assert st_prog["deliverable_progress"]["pct"] > 0

    # 8. Probation actions: Extend +30d, then Confirm
    r_ext = client.post(f"/api/contracts/{doc_id}/probation/action", headers=hdrs, json={"action": "extend", "extend_days": 30})
    assert r_ext.status_code == 200
    r_conf = client.post(f"/api/contracts/{doc_id}/probation/action", headers=hdrs, json={"action": "confirm", "note": "Exceeded expectations"})
    assert r_conf.status_code == 200
    assert r_conf.get_json()["key_term"]["status"] == "met"

    # 9. Project rollup API & Project Detail Dossier page show our contract
    r_pd = client.get(f"/api/projects/{proj_id}")
    assert r_pd.status_code == 200
    assert len(r_pd.get_json()["contracts"]) == 1

    r_pd_html = client.get(f"/projects/{proj_id}")
    assert r_pd_html.status_code == 200
    assert b"HR Q4 Engineering Onboarding" in r_pd_html.data
    assert b"Employment Agreement" in r_pd_html.data


def test_in_module_letterhead_and_template_apply(pg_app, contract_env):
    """Verify selecting/creating & applying Official Letterhead and applying Contract Templates directly in-studio."""
    user_a = contract_env["user_a"]
    doc = contract_env["doc"]
    hdrs = {"X-Requested-With": "fetch"}
    client = _client_for(pg_app, user_a)

    # 1. State exposes letterhead presets, published contract templates, AND approved clauses
    st = client.get(f"/api/contracts/{doc.id}/state").get_json()
    assert len(st["letterhead_presets"]) >= 4
    assert len(st["templates"]) >= 5
    assert len(st["clauses"]) >= 8
    assert all(c["body"] for c in st["clauses"])
    assert st["active_letterhead"] is None

    # 2. Quick-create & apply an official letterhead from a preset right inside the contract
    preset_slug = st["letterhead_presets"][0]["slug"]
    r_lh = client.post(
        f"/api/contracts/{doc.id}/letterhead",
        headers=hdrs,
        json={"preset_slug": preset_slug},
    )
    assert r_lh.status_code == 200
    lh_id = r_lh.get_json()["letterhead"]["id"]

    st2 = client.get(f"/api/contracts/{doc.id}/state").get_json()
    assert st2["active_letterhead"] is not None
    assert st2["active_letterhead"]["id"] == lh_id
    assert "tsd-letterhead-header" in st2["active_letterhead"]["header_html"]

    # 3. Exported PDF contains BOTH the vector Official Letterhead AND full contract content
    from pypdf import PdfReader

    r_pdf = client.get(f"/api/contracts/{doc.id}/pdf")
    assert r_pdf.status_code == 200
    assert r_pdf.data.startswith(b"%PDF-")
    reader = PdfReader(io.BytesIO(r_pdf.data))
    page1_txt = reader.pages[0].extract_text() or ""
    assert "MERIDIAN HOLDINGS LIMITED" in page1_txt
    assert "Master Service Agreement" in page1_txt
    assert "Initial draft clause" in page1_txt

    # 4. Apply a Contract Template (Project SOW) directly onto this existing contract
    sow_tpl = next(t for t in st["templates"] if t["contract_type"] == "sow")
    r_apply = client.post(
        f"/api/contracts/{doc.id}/apply-template",
        headers=hdrs,
        json={
            "template_id": sow_tpl["id"],
            "mode": "replace",
            "seed_key_terms": True,
            "seed_deliverables": True,
            "variables": {"counterparty_name": "Meridian Systems", "deal_value": "185,000"},
        },
    )
    assert r_apply.status_code == 200
    res = r_apply.get_json()
    assert res["added_terms"] >= 1
    assert res["added_deliverables"] >= 1

    st3 = client.get(f"/api/contracts/{doc.id}/state").get_json()
    assert "Meridian Systems" in st3["doc"]["html"]
    assert st3["workflow"]["contract_type"] == "sow"
    assert len(st3["deliverables"]) >= 1

    # 5. Remove letterhead cleanly
    r_rm = client.post(f"/api/contracts/{doc.id}/letterhead", headers=hdrs, json={"letterhead_id": None})
    assert r_rm.status_code == 200
    assert client.get(f"/api/contracts/{doc.id}/state").get_json()["active_letterhead"] is None


def test_external_signed_contract_extract_and_upload(pg_app, contract_env):
    """Verify uploading an already-signed external PDF extracts metadata and files it into Vault + EvidenceRetention."""
    from app.services.tsd_pdf import render_html_to_pdf

    user_a = contract_env["user_a"]
    hdrs = {"X-Requested-With": "fetch"}
    client = _client_for(pg_app, user_a)

    # Build a realistic signed external PDF
    sample_pdf = render_html_to_pdf(
        html=(
            "<h1>EMPLOYMENT AGREEMENT — 90-DAY PROBATION</h1>"
            "<p>This Employment Agreement is entered into between TrustSeal Corp and Jane Wanjiku, "
            "effective 2026-12-01, with annual compensation of USD 145,000.</p>"
            "<p>Employee is subject to a 90-day probation period. This Agreement shall be governed by the laws of Kenya.</p>"
            "<p>Signed by: Jane Wanjiku</p><p>Authorized Signatory: David Ochieng</p>"
        ),
        title="Employment Agreement — Jane Wanjiku",
        document_id=999,
        version=1,
        tenant_id=user_a.organization_id,
    )

    # 1. Extract metadata preview
    r_ex = client.post(
        "/api/contracts/extract",
        headers=hdrs,
        data={"file": (io.BytesIO(sample_pdf), "jane-wanjiku-signed.pdf")},
        content_type="multipart/form-data",
    )
    assert r_ex.status_code == 200
    ex = r_ex.get_json()["extracted"]
    assert ex["contract_type"] == "employment_probation"
    assert ex["currency"] == "USD"
    assert ex["deal_value"] == "145,000"
    assert ex["effective_date"] == "2026-12-01"
    assert ex["governing_law"] == "Kenya"
    assert ex["probation_days"] == 90
    assert len(ex["sha256"]) == 64

    # 2. Upload & File the signed contract record
    r_up = client.post(
        "/api/contracts/upload",
        headers=hdrs,
        data={
            "file": (io.BytesIO(sample_pdf), "jane-wanjiku-signed.pdf"),
            "title": ex["title"],
            "contract_type": ex["contract_type"],
            "counterparty_name": "Jane Wanjiku",
            "currency": ex["currency"],
            "deal_value": ex["deal_value"],
            "effective_date": ex["effective_date"],
            "governing_law": ex["governing_law"],
            "probation_days": str(ex["probation_days"]),
            "contract_status": "SIGNED",
            "notes": "Countersigned wet-ink copy",
        },
        content_type="multipart/form-data",
    )
    assert r_up.status_code == 201
    filed = r_up.get_json()
    assert filed["contract_status"] == "SIGNED"
    assert filed["evidence_retention_id"] is not None
    assert filed["execution_sha256"] == ex["sha256"]

    # 3. Verify state has Probation Key Term & exact original signed PDF is served back bit-for-bit
    doc_id = filed["document_id"]
    st = client.get(f"/api/contracts/{doc_id}/state").get_json()
    assert st["workflow"]["contract_status"] == "SIGNED"
    assert st["probation_term"] is not None
    assert st["probation_term"]["numeric_value"] == 90

    r_pdf = client.get(f"/api/contracts/{doc_id}/pdf")
    assert r_pdf.status_code == 200
    assert r_pdf.data == sample_pdf


def test_100_letterhead_presets_and_contract_stamp_gate(pg_app, contract_env):
    """Verify 100 Premium Letterhead Presets (incl. VitalWorks, VitalWills, VitalReturns) and Stamp attachment."""
    from app.models.tsd_letterhead import LETTERHEAD_PRESETS

    assert len(LETTERHEAD_PRESETS) == 100
    cats = [p["category"] for p in LETTERHEAD_PRESETS]
    assert cats.count("VitalWorks") == 12
    assert cats.count("VitalWills") == 12
    assert cats.count("VitalReturns") == 12

    user_a = contract_env["user_a"]
    doc = contract_env["doc"]
    hdrs = {"X-Requested-With": "fetch"}
    client = _client_for(pg_app, user_a)

    # State returns all 100 presets & auto-seeded corporate stamps
    st = client.get(f"/api/contracts/{doc.id}/state").get_json()
    assert len(st["letterhead_presets"]) == 100
    assert len(st["stamps"]) >= 3
    assert st["workflow"]["stamp_id"] is None

    # Create & apply a VitalWills preset letterhead
    vw_slug = next(p["slug"] for p in st["letterhead_presets"] if p["category"] == "VitalWills")
    assert client.post(f"/api/contracts/{doc.id}/letterhead", headers=hdrs, json={"preset_slug": vw_slug}).status_code == 200

    # Attach corporate stamp -> unlocks post-stamp verification
    stamp_id = st["stamps"][0]["id"]
    r_st = client.post(f"/api/contracts/{doc.id}/stamp", headers=hdrs, json={"stamp_id": stamp_id})
    assert r_st.status_code == 200
    assert r_st.get_json()["workflow"]["stamp_id"] == stamp_id

    # Project Portfolio page renders cleanly
    r_port = client.get("/projects")
    assert r_port.status_code == 200
    assert b"Project Portfolio" in r_port.data


def test_1050_full_length_contract_templates_catalog(pg_app, contract_env):
    """Verify 1,050+ full-length (14-article) Contract Templates catalog, search, preview, apply & instantiate."""
    user_a = contract_env["user_a"]
    doc = contract_env["doc"]
    hdrs = {"X-Requested-With": "fetch"}
    client = _client_for(pg_app, user_a)

    # 1. Catalog search endpoint exposes 1,050+ templates across 15 categories
    r_cat = client.get("/api/contract-templates/catalog?per_page=24")
    assert r_cat.status_code == 200
    data = r_cat.get_json()
    assert data["catalog_total"] >= 1050
    assert len(data["categories"]) == 15
    cat_names = {c["category"] for c in data["categories"]}
    assert "VitalWorks Enterprise Suite" in cat_names
    assert "VitalWills Estate & Fiduciary" in cat_names
    assert "VitalReturns Tax & Fiscal" in cat_names

    # 2. Search & inspect a full-length VitalWills Last Will template -> 14 articles, >= 1,000 words
    r_q = client.get("/api/contract-templates/catalog?q=VitalWills&category=VitalWills%20Estate%20%26%20Fiduciary")
    assert r_q.status_code == 200
    vw_slug = r_q.get_json()["items"][0]["catalog_slug"]

    r_det = client.get(f"/api/contract-templates/catalog/{vw_slug}")
    assert r_det.status_code == 200
    body_html = r_det.get_json()["template"]["body_html"]
    assert "RECITALS" in body_html
    assert "14. General Provisions" in body_html
    assert "IN WITNESS WHEREOF" in body_html
    assert len(body_html.split()) >= 900

    # 3. Apply a full-length VitalReturns Tax template directly into an existing contract
    r_vr = client.get("/api/contract-templates/catalog?category=VitalReturns%20Tax%20%26%20Fiscal")
    vr_slug = r_vr.get_json()["items"][0]["catalog_slug"]
    r_app = client.post(
        f"/api/contracts/{doc.id}/apply-template",
        headers=hdrs,
        json={
            "catalog_slug": vr_slug,
            "mode": "replace",
            "variables": {"counterparty_name": "Acacia Holdings Ltd", "deal_value": "320,000"},
        },
    )
    assert r_app.status_code == 200
    assert r_app.get_json()["added_terms"] >= 1
    st = client.get(f"/api/contracts/{doc.id}/state").get_json()
    assert "Acacia Holdings Ltd" in st["doc"]["html"]
    assert "14. General Provisions" in st["doc"]["html"]

    # 4. Instantiate a brand-new contract from a catalog slug directly into a Project
    r_inst = client.post(
        f"/api/contract-templates/catalog/{vw_slug}/instantiate",
        headers=hdrs,
        json={"variables": {"counterparty_name": "Estate of J. Kamau", "deal_value": "500,000"}},
    )
    assert r_inst.status_code == 201
    assert r_inst.get_json()["document_id"] != doc.id


def test_business_in_a_box_1080_company_document_templates(pg_app, contract_env):
    """Verify 1,080+ Business-in-a-Box Company Document Templates, search, and TSD creation."""
    user_a = contract_env["user_a"]
    hdrs = {"X-Requested-With": "fetch"}
    client = _client_for(pg_app, user_a)

    # 1. Catalog API returns 1,185 documents across 17 departments
    # (1,080 corporate docs + 30 URSB Uganda OBRS + 55 Policies & Guidelines + 20 SACCO Manuals)
    r_bib = client.get("/api/tsd/templates/catalog?per_page=24")
    assert r_bib.status_code == 200
    data = r_bib.get_json()
    assert data["catalog_total"] == 1185
    assert len(data["categories"]) == 17
    cats = {c["category"] for c in data["categories"]}
    assert "Business Planning & Strategy" in cats
    assert "Board & Corporate Governance" in cats
    assert "Human Resources & People Ops" in cats
    assert "Finance, Accounting & Credit" in cats
    assert "VitalWorks, VitalWills & VitalReturns Docs" in cats
    assert "URSB & Uganda Companies Act (OBRS)" in cats
    assert "Corporate Policies & Guidelines" in cats
    assert "Organization-Type Policies & Guidelines" in cats
    assert "Sector & Industry Policies & Guidelines" in cats
    assert "SACCO Policies & Operations Manuals" in cats

    # 1b. URSB OBRS search returns Form 18, BO Form 1, etc. with Republic of Uganda statutory HTML
    r_ursb = client.get("/api/tsd/templates/catalog?category=URSB%20%26%20Uganda%20Companies%20Act%20(OBRS)&per_page=50")
    assert r_ursb.status_code == 200
    ursb_data = r_ursb.get_json()
    assert ursb_data["total"] == 30
    assert any("THE REPUBLIC OF UGANDA" in it["preview_html"] for it in ursb_data["items"])

    # 1c. Comprehensive Company Policies & Guidelines across Corporate (25), Org-Types (12) & Sectors (18)
    r_pol_corp = client.get("/api/tsd/templates/catalog?category=Corporate%20Policies%20%26%20Guidelines&per_page=50")
    assert r_pol_corp.status_code == 200 and r_pol_corp.get_json()["total"] == 25
    r_pol_org = client.get("/api/tsd/templates/catalog?category=Organization-Type%20Policies%20%26%20Guidelines&per_page=50")
    assert r_pol_org.status_code == 200 and r_pol_org.get_json()["total"] == 12
    r_pol_sec = client.get("/api/tsd/templates/catalog?category=Sector%20%26%20Industry%20Policies%20%26%20Guidelines&per_page=50")
    assert r_pol_sec.status_code == 200 and r_pol_sec.get_json()["total"] == 18
    pol_item = r_pol_sec.get_json()["items"][0]
    assert "12. Formal Institutional Adoption" in pol_item["preview_html"]
    r_pol_inst = client.post(f"/api/tsd/from-template/{pol_item['slug']}", headers=hdrs, json={})
    assert r_pol_inst.status_code == 201 and r_pol_inst.get_json()["id"] > 0

    # 1d. Complete SACCO Policies & Operations Manuals (20 docs) + 1,000+ Stamp Templates Catalog
    r_sacco = client.get("/api/tsd/templates/catalog?category=SACCO%20Policies%20%26%20Operations%20Manuals&per_page=50")
    assert r_sacco.status_code == 200 and r_sacco.get_json()["total"] == 20
    r_st = client.get("/api/tsd-stamps/templates/catalog?per_page=16")
    assert r_st.status_code == 200
    st_data = r_st.get_json()
    assert st_data["catalog_total"] >= 1000
    assert len(st_data["styles"]) == 10
    r_st_sacco = client.get("/api/tsd-stamps/templates/catalog?q=SACCO&style=notary-starburst-seal")
    assert r_st_sacco.status_code == 200 and r_st_sacco.get_json()["total"] >= 1
    st_slug = r_st_sacco.get_json()["items"][0]["slug"]
    r_st_create = client.post(f"/api/tsd-stamps/from-template/{st_slug}", headers=hdrs, json={})
    assert r_st_create.status_code == 201

    # 2. Search & instantiate a Business-in-a-Box document directly into TrustSeal Documents
    r_q = client.get("/api/tsd/templates/catalog?q=Board%20Meeting%20Minutes")
    assert r_q.status_code == 200
    slug = r_q.get_json()["items"][0]["slug"]

    r_create = client.post(f"/api/tsd/from-template/{slug}", headers=hdrs, json={})
    assert r_create.status_code == 201
    assert r_create.get_json()["id"] > 0

    # 3. Templates Gallery page renders cleanly with Company Documents, Contracts & Full-Page Preview Modal
    r_hub = client.get("/templates")
    assert r_hub.status_code == 200
    assert b"Template Gallery" in r_hub.data
    assert b"Company Documents" in r_hub.data
    assert b"tpl-preview-modal" in r_hub.data
    assert b"Business-in-a-Box" not in r_hub.data
    assert "preview_html" in data["items"][0] and "<h1>" in data["items"][0]["preview_html"]

    # 4. Both /templates/tsd/<slug>/use AND /templates/builtin/<slug>/use work (zero 404s)
    r_builtin = client.post(f"/templates/builtin/{slug}/use", follow_redirects=False)
    assert r_builtin.status_code in (302, 303)

    # 5. Contracts File menu contains only Contract-specific actions (no Letterhead/Stamp/Forensic links)
    r_ct = client.get("/contracts")
    assert r_ct.status_code == 200
    assert b"Export portfolio CSV" in r_ct.data
    assert b'data-mcmd="letterheads"' not in r_ct.data
    assert b'data-mcmd="stamps"' not in r_ct.data
    assert b'data-mcmd="verify"' not in r_ct.data


def test_project_management_tasks_risks_link_contract_and_health(pg_app, contract_env):
    """Verify full Project Management Module: Tasks CRUD, RAID Risks CRUD, TSD Contract linking, Health RAG & tenant isolation."""
    user_a = contract_env["user_a"]
    user_b = contract_env["user_b"]
    doc = contract_env["doc"]
    hdrs = {"X-Requested-With": "fetch"}
    client_a = _client_for(pg_app, user_a)
    client_b = _client_for(pg_app, user_b)

    # 1. Create a Project
    r_prj = client_a.post(
        "/api/projects",
        headers=hdrs,
        json={
            "name": "Core Banking Modernization",
            "category": "procurement",
            "budget_amount": 250000,
            "currency": "USD",
            "status": "active",
            "start_date": "2026-10-01",
            "end_date": "2027-06-30",
        },
    )
    assert r_prj.status_code == 201
    proj_id = r_prj.get_json()["project"]["id"]

    # 2. Link an existing TSD Contract to the Project
    r_link = client_a.post(
        f"/api/projects/{proj_id}/link-contract",
        headers=hdrs,
        json={"document_id": doc.id},
    )
    assert r_link.status_code == 200
    assert r_link.get_json()["project_id"] == proj_id

    # Cross-tenant check: user_b cannot access or mutate user_a's project
    client_b = _client_for(pg_app, user_b)
    assert client_b.get(f"/api/projects/{proj_id}/tasks").status_code == 404
    assert client_b.post(f"/api/projects/{proj_id}/tasks", headers=hdrs, json={"title": "Sneaky"}).status_code == 404
    assert client_b.get(f"/api/projects/{proj_id}/risks").status_code == 404
    assert client_b.post(f"/api/projects/{proj_id}/link-contract", headers=hdrs, json={"document_id": doc.id}).status_code == 404

    # 3. Tasks CRUD (linked to contract)
    client_a = _client_for(pg_app, user_a)
    r_t1 = client_a.post(
        f"/api/projects/{proj_id}/tasks",
        headers=hdrs,
        json={
            "title": "Verify Phase 1 Contract Milestones",
            "workstream": "Governance",
            "priority": "high",
            "status": "todo",
            "assignee_name": "Alice PM",
            "due_date": "2027-01-15",
            "linked_document_id": doc.id,
        },
    )
    assert r_t1.status_code == 201
    t1_id = r_t1.get_json()["task"]["id"]
    assert r_t1.get_json()["task"]["linked_document_id"] == doc.id

    r_tlist = client_a.get(f"/api/projects/{proj_id}/tasks")
    assert r_tlist.status_code == 200
    assert len(r_tlist.get_json()["tasks"]) == 1

    r_tupd = client_a.patch(
        f"/api/projects/{proj_id}/tasks/{t1_id}",
        headers=hdrs,
        json={"status": "in_progress", "priority": "urgent"},
    )
    assert r_tupd.status_code == 200
    assert r_tupd.get_json()["task"]["status"] == "in_progress"
    assert r_tupd.get_json()["task"]["priority"] == "urgent"

    # 4. RAID Risks CRUD
    r_r1 = client_a.post(
        f"/api/projects/{proj_id}/risks",
        headers=hdrs,
        json={
            "title": "Vendor delivery SLA exposure",
            "item_type": "risk",
            "severity": "high",
            "status": "open",
            "owner_name": "Legal Counsel",
            "mitigation_plan": "Invoke clause 7.2 service credits",
            "linked_document_id": doc.id,
        },
    )
    assert r_r1.status_code == 201
    r1_id = r_r1.get_json()["risk"]["id"]

    r_rlist = client_a.get(f"/api/projects/{proj_id}/risks")
    assert r_rlist.status_code == 200
    assert len(r_rlist.get_json()["risks"]) == 1

    # 5. Portfolio & Dossier HTML pages render with Health RAG, Status Board, Tasks & RAID tabs
    r_port = client_a.get("/projects")
    assert r_port.status_code == 200
    assert b"Core Banking Modernization" in r_port.data
    assert b"Status Board" in r_port.data
    assert b"At Risk" in r_port.data

    r_det = client_a.get(f"/projects/{proj_id}")
    assert r_det.status_code == 200
    assert b"Tasks &amp; Workstreams" in r_det.data
    assert b"Risks &amp; Issues" in r_det.data
    assert b"Verify Phase 1 Contract Milestones" in r_det.data
    assert b"Vendor delivery SLA exposure" in r_det.data
    assert b"Project Settings" in r_det.data

    # 6. Mitigate risk & delete task/risk cleanly
    r_rupd = client_a.patch(
        f"/api/projects/{proj_id}/risks/{r1_id}",
        headers=hdrs,
        json={"status": "mitigated"},
    )
    assert r_rupd.status_code == 200
    assert r_rupd.get_json()["risk"]["status"] == "mitigated"

    assert client_a.delete(f"/api/projects/{proj_id}/tasks/{t1_id}", headers=hdrs).status_code == 200
    assert client_a.delete(f"/api/projects/{proj_id}/risks/{r1_id}", headers=hdrs).status_code == 200
    assert len(client_a.get(f"/api/projects/{proj_id}/tasks").get_json()["tasks"]) == 0
    assert len(client_a.get(f"/api/projects/{proj_id}/risks").get_json()["risks"]) == 0


