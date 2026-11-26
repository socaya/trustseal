"""Standalone Workspace HTML views for shared Media Library, Letterheads & Signed Contracts.

* ``/contracts/signed`` — Signed & finalized contracts vault
* ``/letterheads``      — Tenant Official Letterheads workspace module
* ``/media``            — Shared Tenant Media Library workspace module
"""
from __future__ import annotations

from datetime import datetime
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.orm.attributes import flag_modified

from app.extensions import db
from app.models.contract_workflow import (
    CONTRACT_STATUSES,
    ContractDeliverable,
    ContractKeyTerm,
    ContractObligation,
    ContractTemplate,
    ContractWorkflow,
    Project,
    WORKFLOW_STAGES,
    STAGE_LABELS,
    ensure_contract_workflow_table,
)
from app.blueprints.contracts.lifecycle_service import (
    actor_label as _actor_label,
    append_workflow_event as _append_wf_event,
    close_and_seal_contract,
    compute_deliverable_progress,
    ensure_default_project,
    ensure_default_templates,
    get_or_create_workflow as _get_or_create_workflow,
    normalize_stage as _normalize_contract_stage,
    stage_to_canonical_status,
    transition_stage,
)
from app.models.documents.document_template import DocumentTemplate
from app.models.tsd_document import TSDocument
from app.models.tsd_stamp_insertion import TSDStampInsertion
from app.models.user import User


workspace_assets_views = Blueprint("workspace_assets_views", __name__)


def _actor():
    if not current_user.is_authenticated:
        abort(401)
    if current_user.organization_id is None:
        abort(403, description="organization_required")
    return current_user


CONTRACT_LIFECYCLE_STAGES = list(WORKFLOW_STAGES)


@workspace_assets_views.route("/contracts", methods=["GET"])
@workspace_assets_views.route("/contracts/signed", methods=["GET"])
@login_required
def signed_contracts_page():
    actor = _actor()
    org_id = actor.organization_id
    ensure_contract_workflow_table()
    default_proj = ensure_default_project(org_id, actor)
    contract_templates = ensure_default_templates(org_id, actor)
    projects_list = (
        Project.query.filter_by(organization_id=org_id)
        .order_by(Project.is_default.desc(), Project.name.asc())
        .all()
    )
    proj_map = {p.id: p for p in projects_list}
    selected_project_id = request.args.get("project", type=int)

    tsd_rows = (
        TSDocument.query
        .filter(TSDocument.organization_id == org_id, TSDocument.deleted_at.is_(None))
        .order_by(TSDocument.updated_at.desc())
        .limit(400)
        .all()
    )

    wf_map = {
        w.document_id: w
        for w in ContractWorkflow.query.filter_by(organization_id=org_id).all()
    }
    deliv_by_wf: dict[int, list[ContractDeliverable]] = {}
    for dl in ContractDeliverable.query.filter_by(organization_id=org_id).all():
        deliv_by_wf.setdefault(dl.contract_id, []).append(dl)
    prob_by_wf: dict[int, ContractKeyTerm] = {}
    for kt in ContractKeyTerm.query.filter_by(organization_id=org_id, category="probation").all():
        prob_by_wf[kt.contract_id] = kt

    stamp_counts = dict(
        db.session.query(
            TSDStampInsertion.document_id,
            func.count(TSDStampInsertion.id),
        )
        .filter(
            TSDStampInsertion.organization_id == org_id,
            TSDStampInsertion.document_id.isnot(None),
            TSDStampInsertion.revoked_at.is_(None),
        )
        .group_by(TSDStampInsertion.document_id)
        .all()
    )

    creator_ids = {r.created_by_id for r in tsd_rows if r.created_by_id}

    env_rows = []
    doc_titles = {}
    try:
        from app.models.document import Document
        from app.models.signing_envelope import SigningEnvelope
        env_rows = (
            SigningEnvelope.query
            .filter(SigningEnvelope.organization_id == org_id)
            .order_by(SigningEnvelope.created_at.desc())
            .limit(400)
            .all()
        )
        for ev in env_rows:
            if ev.created_by_id:
                creator_ids.add(ev.created_by_id)
        doc_ids = list({e.document_id for e in env_rows if e.document_id})
        if doc_ids:
            for d in Document.query.filter(Document.id.in_(doc_ids)).all():
                doc_titles[d.id] = d.title or f"Document #{d.id}"
    except Exception:
        env_rows = []

    user_names = {}
    if creator_ids:
        for u in User.query.filter(User.id.in_(list(creator_ids))).all():
            full = (u.get_full_name() or "").strip() if hasattr(u, "get_full_name") else ""
            user_names[u.id] = full or u.username or u.email or f"User #{u.id}"

    contracts = []
    for d in tsd_rows:
        wf = wf_map.get(d.id)
        stage = wf.stage if wf else _normalize_contract_stage(d.status)
        c_status = wf.canonical_status() if wf else stage_to_canonical_status(stage)
        proj = proj_map.get(wf.project_id) if (wf and wf.project_id) else default_proj
        signers = (wf.signers_json or []) if wf else []
        signed_cnt = sum(1 for s in signers if s.get("status") == "signed")
        prog = compute_deliverable_progress(deliv_by_wf.get(wf.id, [])) if wf else {"total": 0, "pct": 0}
        prob = prob_by_wf.get(wf.id) if wf else None
        contracts.append({
            "id": d.id,
            "source": "tsd",
            "source_label": "TS Document",
            "project_id": proj.id if proj else default_proj.id,
            "project_code": proj.project_code if proj else default_proj.project_code,
            "project_name": proj.name if proj else default_proj.name,
            "contract_number": (wf.contract_number if (wf and wf.contract_number) else f"CTR-{d.id:04d}"),
            "contract_type": (wf.contract_type if wf else "msa"),
            "contract_status": c_status,
            "title": d.title,
            "counterparty": (wf.counterparty_name or "") if wf else "",
            "deal_value": (f"{wf.currency} {wf.deal_value}" if (wf and wf.deal_value) else ""),
            "effective_date": (wf.effective_date or "") if wf else "",
            "expiration_date": (wf.expiration_date or "") if wf else "",
            "renewal_type": (wf.renewal_type or "none") if wf else "none",
            "owner": user_names.get(d.created_by_id, f"User #{d.created_by_id}"),
            "status": (d.status or "draft").lower(),
            "stage": stage,
            "stage_label": STAGE_LABELS.get(stage, "Draft"),
            "stamps": stamp_counts.get(d.id, 0),
            "signers_total": len(signers),
            "signers_signed": signed_cnt,
            "deliverables_total": prog["total"],
            "deliverables_pct": prog["pct"],
            "probation_status": prob.status if prob else "",
            "probation_end": prob.end_date if prob else "",
            "evidence_retention_id": wf.evidence_retention_id if wf else None,
            "version": getattr(d, "version", 1),
            "updated_at": d.updated_at.strftime("%Y-%m-%d %H:%M") if d.updated_at else "",
            "updated_iso": d.updated_at.isoformat() if d.updated_at else "",
            "open_url": f"/documents/library/{d.id}",
            "workflow_url": f"/contracts/{d.id}/workflow",
        })

    for ev in env_rows:
        ts = getattr(ev, "prepared_at", None) or ev.created_at
        raw_st = (ev.state or "draft").lower()
        stage = _normalize_contract_stage(raw_st)
        c_status = stage_to_canonical_status(stage)
        contracts.append({
            "id": ev.id,
            "source": "envelope",
            "source_label": "Signing Envelope",
            "project_id": default_proj.id,
            "project_code": default_proj.project_code,
            "project_name": default_proj.name,
            "contract_number": f"ENV-{ev.id:04d}",
            "contract_type": "envelope",
            "contract_status": c_status,
            "title": doc_titles.get(ev.document_id, f"Envelope #{ev.id}"),
            "counterparty": "",
            "deal_value": "",
            "effective_date": "",
            "expiration_date": "",
            "renewal_type": "none",
            "owner": user_names.get(ev.created_by_id, f"User #{ev.created_by_id}"),
            "status": raw_st,
            "stage": stage,
            "stage_label": STAGE_LABELS.get(stage, "Draft"),
            "stamps": 0,
            "signers_total": 0,
            "signers_signed": 0,
            "deliverables_total": 0,
            "deliverables_pct": 0,
            "probation_status": "",
            "probation_end": "",
            "evidence_retention_id": None,
            "version": 1,
            "updated_at": ts.strftime("%Y-%m-%d %H:%M") if ts else "",
            "updated_iso": ts.isoformat() if ts else "",
            "open_url": f"/documents/{ev.document_id}" if ev.document_id else "#",
            "workflow_url": f"/documents/{ev.document_id}" if ev.document_id else "#",
        })

    contracts.sort(key=lambda c: c["updated_iso"], reverse=True)

    counts = {"all": len(contracts)}
    for key, _lbl in WORKFLOW_STAGES:
        counts[key] = sum(1 for c in contracts if c["stage"] == key)
    status_counts = {"ALL": len(contracts)}
    for skey, _slbl in CONTRACT_STATUSES:
        status_counts[skey] = sum(1 for c in contracts if c["contract_status"] == skey)

    obligations_pending = 0
    try:
        obligations_pending = (
            ContractObligation.query.filter_by(organization_id=org_id)
            .filter(ContractObligation.status != "completed")
            .count()
        )
    except Exception:
        obligations_pending = 0

    kpi = {
        "total": len(contracts),
        "draft": status_counts["DRAFT"],
        "signed": status_counts["SIGNED"],
        "suspended": status_counts["SUSPENDED"],
        "terminated": status_counts["TERMINATED"],
        "in_flight": status_counts["DRAFT"],
        "awaiting_sign": counts.get("signature", 0),
        "active": status_counts["SIGNED"],
        "obligations_pending": obligations_pending,
    }

    letterheads = []
    try:
        from app.models.tsd_letterhead import TSDLetterhead
        lh_rows = (
            TSDLetterhead.query
            .filter_by(organization_id=org_id)
            .order_by(TSDLetterhead.is_default.desc(), TSDLetterhead.updated_at.desc())
            .all()
        )
        letterheads = [{"id": lh.id, "name": lh.name, "is_default": bool(lh.is_default)} for lh in lh_rows]
    except Exception:
        pass

    return render_template(
        "workspace/signed_contracts.html",
        contracts=contracts,
        stages=WORKFLOW_STAGES,
        contract_statuses=CONTRACT_STATUSES,
        status_counts=status_counts,
        counts=counts,
        kpi=kpi,
        projects=[p.to_dict() for p in projects_list],
        selected_project_id=selected_project_id,
        contract_templates=[t.to_dict() for t in contract_templates if t.state == "published"],
        letterheads=letterheads,
        tsd_count=len(tsd_rows),
        env_count=len(env_rows),
        total_stamps=sum(c["stamps"] for c in contracts),
    )


@workspace_assets_views.route("/contracts/<int:doc_id>/stage", methods=["POST"])
@login_required
def update_contract_stage(doc_id: int):
    actor = _actor()
    doc = TSDocument.query.filter_by(id=doc_id, organization_id=actor.organization_id).first()
    if not doc:
        abort(404)
    data = request.get_json(silent=True) or {}
    stage = (data.get("stage") or "").strip().lower()
    wf = _get_or_create_workflow(doc, actor)
    if data.get("counterparty_name"):
        wf.counterparty_name = str(data.get("counterparty_name"))[:200]
    if data.get("letterhead_id"):
        try:
            wf.letterhead_id = int(data["letterhead_id"])
        except (TypeError, ValueError):
            pass
    note = (data.get("note") or "").strip()
    ok, err = transition_stage(doc=doc, wf=wf, actor=actor, target_stage=stage, note=note)
    if not ok:
        return jsonify({"error": err}), 400
    db.session.commit()
    return jsonify({"ok": True, "id": doc.id, "stage": wf.stage, "status": doc.status, "workflow": wf.to_dict()})


@workspace_assets_views.route("/contracts/<int:doc_id>", methods=["GET"])
@workspace_assets_views.route("/contracts/<int:doc_id>/workflow", methods=["GET"])
@login_required
def contract_workflow_page(doc_id: int):
    actor = _actor()
    doc = TSDocument.query.filter_by(id=doc_id, organization_id=actor.organization_id).first()
    if not doc:
        abort(404)
    wf = _get_or_create_workflow(doc, actor)
    stamps = []
    try:
        from app.models.tsd_stamp import TSDStamp
        for s in TSDStamp.query.filter_by(organization_id=actor.organization_id).order_by(TSDStamp.updated_at.desc()).limit(50).all():
            stamps.append({"id": s.id, "name": s.name, "kind": s.kind, "svg": s.svg or ""})
    except Exception:
        pass
    return render_template(
        "workspace/contract_workflow.html",
        doc=doc,
        wf=wf.to_dict(),
        stages=WORKFLOW_STAGES,
        stamps=stamps,
        actor_name=_actor_label(actor),
        actor_email=getattr(actor, "email", "") or "",
    )


@workspace_assets_views.route("/contracts/<int:doc_id>/workflow/meta", methods=["POST"])
@login_required
def update_contract_workflow_meta(doc_id: int):
    actor = _actor()
    doc = TSDocument.query.filter_by(id=doc_id, organization_id=actor.organization_id).first()
    if not doc:
        abort(404)
    wf = _get_or_create_workflow(doc, actor)
    data = request.get_json(silent=True) or {}
    for field, attr, limit in (
        ("counterparty_name", "counterparty_name", 200),
        ("deal_value", "deal_value", 64),
        ("currency", "currency", 12),
        ("effective_date", "effective_date", 32),
        ("governing_law", "governing_law", 120),
    ):
        if field in data:
            setattr(wf, attr, str(data.get(field) or "").strip()[:limit])
    if "stamp_id" in data:
        wf.stamp_id = int(data["stamp_id"]) if data.get("stamp_id") else None
    if isinstance(data.get("checklist"), dict):
        chk = dict(wf.checklist_json or {})
        for k, v in data["checklist"].items():
            chk[str(k)] = bool(v)
        wf.checklist_json = chk
        flag_modified(wf, "checklist_json")
    db.session.commit()
    return jsonify({"ok": True, "workflow": wf.to_dict()})


@workspace_assets_views.route("/contracts/<int:doc_id>/workflow/signers", methods=["POST"])
@login_required
def update_contract_workflow_signers(doc_id: int):
    actor = _actor()
    doc = TSDocument.query.filter_by(id=doc_id, organization_id=actor.organization_id).first()
    if not doc:
        abort(404)
    wf = _get_or_create_workflow(doc, actor)
    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "add").lower()
    signers = list(wf.signers_json or [])

    if action == "add":
        name = str(data.get("name") or "").strip()[:140]
        email = str(data.get("email") or "").strip()[:180]
        role = str(data.get("role") or "Counterparty Signatory").strip()[:120]
        if not name:
            return jsonify({"error": "signer_name_required"}), 400
        sid = f"sig-{int(datetime.utcnow().timestamp() * 1000)}"
        signers.append({
            "id": sid,
            "name": name,
            "email": email,
            "role": role,
            "status": "pending",
            "signed_at": "",
            "signature_text": "",
        })
        _append_wf_event(wf, actor, "Signatory added", f"{name} ({role})")
    elif action == "remove":
        sid = str(data.get("id") or "")
        signers = [s for s in signers if s.get("id") != sid]
        _append_wf_event(wf, actor, "Signatory removed", sid)

    wf.signers_json = signers
    flag_modified(wf, "signers_json")
    db.session.commit()
    return jsonify({"ok": True, "workflow": wf.to_dict()})


@workspace_assets_views.route("/contracts/<int:doc_id>/workflow/sign", methods=["POST"])
@login_required
def sign_contract_workflow_signer(doc_id: int):
    actor = _actor()
    doc = TSDocument.query.filter_by(id=doc_id, organization_id=actor.organization_id).first()
    if not doc:
        abort(404)
    wf = _get_or_create_workflow(doc, actor)
    data = request.get_json(silent=True) or {}
    sid = str(data.get("id") or "")
    sig_text = str(data.get("signature_text") or "").strip()[:140]
    signers = list(wf.signers_json or [])
    matched = None
    for s in signers:
        if s.get("id") == sid:
            s["status"] = "signed"
            s["signed_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
            s["signature_text"] = sig_text or s.get("name") or _actor_label(actor)
            matched = s
            break
    if not matched:
        return jsonify({"error": "signer_not_found"}), 404
    wf.signers_json = signers
    flag_modified(wf, "signers_json")
    if wf.stage in ("draft", "review", "approval"):
        wf.stage = "signature"
    _append_wf_event(wf, actor, "Agreement signed with TrustSeal", f"{matched['name']} · {matched['role']}")
    db.session.commit()
    return jsonify({"ok": True, "workflow": wf.to_dict()})


@workspace_assets_views.route("/contracts/<int:doc_id>/workflow/close-deal", methods=["POST"])
@login_required
def close_contract_deal(doc_id: int):
    actor = _actor()
    doc = TSDocument.query.filter_by(id=doc_id, organization_id=actor.organization_id).first()
    if not doc:
        abort(404)
    wf = _get_or_create_workflow(doc, actor)
    data = request.get_json(silent=True) or {}
    stamp_id = int(data["stamp_id"]) if data.get("stamp_id") else None
    closing_note = str(data.get("note") or "").strip()[:300]
    res = close_and_seal_contract(
        doc=doc, wf=wf, actor=actor, stamp_id=stamp_id, closing_note=closing_note
    )
    return jsonify({"ok": True, **res})


@workspace_assets_views.route("/letterheads", methods=["GET"])
@login_required
def letterheads_page():
    _actor()
    return render_template("stamps/letterheads.html")


@workspace_assets_views.route("/media", methods=["GET"])
@login_required
def media_page():
    _actor()
    return render_template("stamps/media.html")


@workspace_assets_views.route("/templates", methods=["GET", "POST"])
@login_required
def templates_hub_page():
    from app.models.tsd_letterhead import LETTERHEAD_PRESETS, TSDLetterhead
    from app.services.tsd_stamp_templates import list_templates as list_stamp_templates
    from app.services.tsd_templates import list_templates as list_tsd_templates

    actor = _actor()
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()[:200]
        desc = (request.form.get("description") or "").strip()
        content = (request.form.get("content") or "").strip()
        if name:
            row = DocumentTemplate(
                organization_id=actor.organization_id,
                name=name,
                description=desc or None,
                content=content or "",
                state="draft",
                is_active=True,
                created_by=actor.id,
            )
            db.session.add(row)
            db.session.commit()
            flash(f'Template "{name}" created.', "success")
        return redirect(url_for("workspace_assets_views.templates_hub_page"))

    rows = (
        DocumentTemplate.query
        .filter(DocumentTemplate.organization_id == actor.organization_id)
        .order_by(DocumentTemplate.created_at.desc())
        .limit(200)
        .all()
    )
    c_ids = list({r.created_by for r in rows if r.created_by})
    creators = {}
    if c_ids:
        for u in User.query.filter(User.id.in_(c_ids)).all():
            full = (u.get_full_name() or "").strip() if hasattr(u, "get_full_name") else ""
            creators[u.id] = full or u.username or u.email or f"User #{u.id}"

    tsd_templates = list_tsd_templates(include_body=True)
    saved_letterheads = (
        TSDLetterhead.query
        .filter(TSDLetterhead.organization_id == actor.organization_id)
        .order_by(TSDLetterhead.is_default.desc(), TSDLetterhead.updated_at.desc())
        .limit(100)
        .all()
    )
    from app.services.tsd_stamp_templates import get_stamp_catalog_summary
    stamp_summary = get_stamp_catalog_summary()
    from app.services.business_docs_catalog import (
        get_business_doc_categories,
        get_business_docs_catalog,
    )
    from app.models.contract_templates_catalog import (
        get_catalog_categories_summary,
        get_contract_template_catalog,
    )
    bib_total = len(get_business_docs_catalog())
    bib_categories = get_business_doc_categories()
    ctr_total = len(get_contract_template_catalog())
    ctr_categories = get_catalog_categories_summary()

    return render_template(
        "workspace/templates.html",
        templates=rows,
        creators=creators,
        tsd_templates=tsd_templates,
        letterhead_presets=LETTERHEAD_PRESETS,
        saved_letterheads=saved_letterheads,
        stamp_templates=[],
        stamp_total=stamp_summary["total"],
        stamp_categories=stamp_summary["categories"],
        stamp_styles=stamp_summary["styles"],
        bib_total=bib_total,
        bib_categories=bib_categories,
        ctr_total=ctr_total,
        ctr_categories=ctr_categories,
    )


@workspace_assets_views.route("/templates/tsd/<slug>/use", methods=["POST"])
@workspace_assets_views.route("/templates/builtin/<slug>/use", methods=["POST"])
@login_required
def use_builtin_tsd_template(slug: str):
    from app.services.tsd_format import encrypt_content_envelope, pack_content, sha256_hex
    from app.services.tsd_templates import get_template as get_tsd_template

    actor = _actor()
    tpl = get_tsd_template(slug)
    if tpl is None:
        abort(404)

    title = (request.form.get("title") or tpl.title or tpl.name or "Untitled Document").strip()[:240]
    body_html = (getattr(tpl, "body_html", None) or getattr(tpl, "html", None) or "").strip() or f"<h1>{tpl.name}</h1><p></p>"
    tpl_tags = list(getattr(tpl, "tags", None) or [])
    if "template" not in tpl_tags:
        tpl_tags.append("template")
    if tpl.category and tpl.category.lower() not in tpl_tags:
        tpl_tags.append(tpl.category.lower())
    plaintext = pack_content(
        html=body_html,
        description=tpl.description or f"Created from TSD template: {tpl.name}",
        tags=tpl_tags,
        extras={"builtin_template_slug": tpl.slug, "template_name": tpl.name},
    )
    ciphertext = encrypt_content_envelope(plaintext, organization_id=actor.organization_id)
    doc = TSDocument(
        organization_id=actor.organization_id,
        created_by_id=actor.id,
        title=title,
        description=tpl.description or f"Template: {tpl.name}",
        tags=",".join(tpl_tags),
        export_policy="pdf_allowed",
        status="draft",
        ciphertext=ciphertext,
        ciphertext_sha256=sha256_hex(ciphertext),
        plaintext_bytes=len(plaintext),
    )
    db.session.add(doc)
    db.session.commit()
    return redirect(f"/documents/library/{doc.id}")


@workspace_assets_views.route("/templates/<int:tpl_id>/use", methods=["POST"])
@login_required
def use_template_create_tsd(tpl_id: int):
    from app.services.signature_attestations import (
        SignatureAttestationError,
        validate_document_signatures,
    )
    from app.services.tsd_format import (
        encrypt_content_envelope,
        pack_content,
        sanitize_html,
        sha256_hex,
    )

    actor = _actor()
    tpl = db.session.get(DocumentTemplate, tpl_id)
    if tpl is None or tpl.organization_id != actor.organization_id:
        abort(404)

    title = (request.form.get("title") or tpl.name or "Untitled Document").strip()[:240]
    body_html = sanitize_html((tpl.content or "").strip() or f"<h1>{tpl.name}</h1><p></p>")
    try:
        validate_document_signatures(
            html=body_html,
            organization_id=actor.organization_id,
            document_id=None,
        )
    except SignatureAttestationError:
        flash("Template contains an untrusted signature marker and cannot be instantiated.", "danger")
        return redirect(url_for("workspace_assets_views.templates_hub_page"))
    plaintext = pack_content(
        html=body_html,
        description=tpl.description or f"Created from template: {tpl.name}",
        tags=["template"],
        extras={"template_id": tpl.id, "template_name": tpl.name},
    )
    ciphertext = encrypt_content_envelope(plaintext, organization_id=actor.organization_id)
    doc = TSDocument(
        organization_id=actor.organization_id,
        created_by_id=actor.id,
        title=title,
        description=tpl.description or f"Template: {tpl.name}",
        tags="template",
        export_policy="pdf_allowed",
        status="draft",
        ciphertext=ciphertext,
        ciphertext_sha256=sha256_hex(ciphertext),
        plaintext_bytes=len(plaintext),
    )
    db.session.add(doc)
    db.session.commit()
    return redirect(f"/documents/library/{doc.id}")


@workspace_assets_views.route("/tsd/<int:tsd_id>", methods=["GET"])
@login_required
def legacy_tsd_redirect(tsd_id: int):
    return redirect(url_for("tsd_views.edit", tsd_id=tsd_id), code=302)


@workspace_assets_views.route("/templates/<int:tpl_id>/status", methods=["POST"])
@login_required
def update_template_status(tpl_id: int):
    actor = _actor()
    tpl = db.session.get(DocumentTemplate, tpl_id)
    if tpl is None or tpl.organization_id != actor.organization_id:
        abort(404)
    target = (request.form.get("state") or "").strip().lower()
    if target in ("draft", "published", "archived"):
        tpl.state = target
        tpl.is_active = (target != "archived")
        db.session.commit()
        flash(f'Template "{tpl.name}" marked as {target}.', "success")
    return redirect(url_for("workspace_assets_views.templates_hub_page"))


@workspace_assets_views.route("/templates/<int:tpl_id>/delete", methods=["POST"])
@login_required
def delete_template_row(tpl_id: int):
    actor = _actor()
    tpl = db.session.get(DocumentTemplate, tpl_id)
    if tpl is None or tpl.organization_id != actor.organization_id:
        abort(404)
    db.session.delete(tpl)
    db.session.commit()
    flash(f'Template "{tpl.name}" deleted.', "success")
    return redirect(url_for("workspace_assets_views.templates_hub_page"))


@workspace_assets_views.route("/signatures", methods=["GET"])
@login_required
def signatures_hub_page():
    actor = _actor()
    envelopes = []
    counts = {"total": 0, "pending": 0, "completed": 0, "declined": 0}
    eligible_docs = []
    tenant_users = []
    try:
        from app.models.document import Document
        from app.models.document_blob import DocumentBlob
        from app.models.signing_envelope import EnvelopeParticipant, SigningEnvelope

        rows = (
            SigningEnvelope.query
            .filter(SigningEnvelope.organization_id == actor.organization_id)
            .order_by(SigningEnvelope.created_at.desc())
            .limit(200)
            .all()
        )
        env_ids = [r.id for r in rows]
        doc_ids = list({r.document_id for r in rows if r.document_id})
        doc_titles = {}
        if doc_ids:
            for d in Document.query.filter(Document.id.in_(doc_ids)).all():
                doc_titles[d.id] = d.title or f"Document #{d.id}"

        parts_by_env: dict[int, list] = {}
        part_user_ids: set[int] = set()
        if env_ids:
            for p in EnvelopeParticipant.query.filter(EnvelopeParticipant.envelope_id.in_(env_ids)).order_by(EnvelopeParticipant.signing_order.asc()).all():
                parts_by_env.setdefault(p.envelope_id, []).append(p)
                if p.user_id:
                    part_user_ids.add(p.user_id)

        user_map = {}
        if part_user_ids:
            for u in User.query.filter(User.id.in_(part_user_ids)).all():
                full = (u.get_full_name() or "").strip() if hasattr(u, "get_full_name") else ""
                user_map[u.id] = full or u.username or u.email or f"User #{u.id}"

        for ev in rows:
            st = (getattr(ev, "state", None) or "draft").lower()
            counts["total"] += 1
            if st in ("prepared", "completed", "signed"):
                counts["completed"] += 1
            elif st in ("cancelled", "withdrawn", "superseded", "declined", "expired"):
                counts["declined"] += 1
            else:
                counts["pending"] += 1
            parts = parts_by_env.get(ev.id, [])
            envelopes.append({
                "id": ev.id,
                "title": doc_titles.get(ev.document_id, f"Envelope #{ev.id}"),
                "status": st,
                "routing_mode": getattr(ev, "routing_mode", "sequential") or "sequential",
                "participants_count": len(parts),
                "participants_preview": ", ".join(
                    user_map.get(p.user_id, f"User #{p.user_id}")
                    for p in parts[:3]
                ) or "—",
                "created_at": ev.created_at.strftime("%Y-%m-%d %H:%M") if getattr(ev, "created_at", None) else "",
                "created_iso": ev.created_at.isoformat() if getattr(ev, "created_at", None) else "",
                "open_url": f"/documents/{ev.document_id}" if getattr(ev, "document_id", None) else "#",
            })

        # Eligible documents with at least one blob for the composer
        blob_doc_ids = [
            row[0]
            for row in db.session.query(DocumentBlob.document_id).distinct().limit(200).all()
        ]
        if blob_doc_ids:
            eligible_docs = (
                Document.query
                .filter(
                    Document.organization_id == actor.organization_id,
                    Document.deleted_at.is_(None),
                    Document.id.in_(blob_doc_ids),
                )
                .order_by(Document.id.desc())
                .limit(100)
                .all()
            )
        tenant_users = (
            User.query
            .filter(User.organization_id == actor.organization_id, User.is_active.is_(True))
            .order_by(User.email.asc())
            .limit(150)
            .all()
        )
    except Exception:
        pass
    registered_signatures = []
    usage_logs = []
    try:
        from app.models.esignature import SignatureProfile
        from app.models.signature_governance import (
            SignatureApprovalState,
            SignatureUsageLog,
            compute_ts_signature_seal,
            ensure_signature_governance_tables,
        )
        ensure_signature_governance_tables()

        org_user_ids = [u.id for u in tenant_users] if tenant_users else [actor.id]
        user_by_id = {u.id: u for u in tenant_users}
        sig_rows = (
            SignatureProfile.query
            .filter(SignatureProfile.user_id.in_(org_user_ids))
            .order_by(SignatureProfile.is_default.desc(), SignatureProfile.created_at.desc())
            .limit(200)
            .all()
        )
        sig_ids = [s.id for s in sig_rows]
        states_by_sig = {}
        if sig_ids:
            for st in SignatureApprovalState.query.filter(SignatureApprovalState.signature_profile_id.in_(sig_ids)).all():
                states_by_sig[st.signature_profile_id] = st

        for sp in sig_rows:
            u = user_by_id.get(sp.user_id) or db.session.get(User, sp.user_id)
            full = (u.get_full_name() or "").strip() if (u and hasattr(u, "get_full_name")) else ""
            st = states_by_sig.get(sp.id)
            _, ts_fp = compute_ts_signature_seal(
                organization_id=actor.organization_id,
                signature_profile_id=sp.id,
                owner_user_id=sp.user_id,
                signature_data=sp.signature_data or "",
            )
            registered_signatures.append({
                "id": sp.id,
                "name": sp.name,
                "signature_type": sp.signature_type or "drawn",
                "initials_data": sp.initials_data or "",
                "is_default": bool(sp.is_default),
                "user_id": sp.user_id,
                "is_mine": sp.user_id == actor.id,
                "staff_name": full or (u.username if u else "") or (u.email if u else f"User #{sp.user_id}"),
                "staff_email": (u.email if u else "") or "",
                "approval_status": st.approval_status if st else "pending",
                "capture_engine": st.capture_engine if st else (sp.signature_type or "ts_hq_engine"),
                "device_name": (st.device_name if st else "") or "",
                "ts_fingerprint": ts_fp,
                "created_at": sp.created_at.strftime("%Y-%m-%d %H:%M") if sp.created_at else "—",
            })

        log_rows = (
            SignatureUsageLog.query
            .filter(SignatureUsageLog.organization_id == actor.organization_id)
            .order_by(SignatureUsageLog.created_at.desc())
            .limit(100)
            .all()
        )
        sig_name_map = {s["id"]: s["name"] for s in registered_signatures}
        for lg in log_rows:
            own = user_by_id.get(lg.owner_user_id) or db.session.get(User, lg.owner_user_id)
            req = user_by_id.get(lg.requester_user_id) or db.session.get(User, lg.requester_user_id)
            own_name = ((own.get_full_name() or "").strip() if (own and hasattr(own, "get_full_name")) else "") or (own.email if own else f"User #{lg.owner_user_id}")
            req_name = ((req.get_full_name() or "").strip() if (req and hasattr(req, "get_full_name")) else "") or (req.email if req else f"User #{lg.requester_user_id}")
            status_eff = "expired" if (lg.status == "otp_pending" and lg.is_expired()) else lg.status
            usage_logs.append({
                "id": lg.id,
                "signature_name": sig_name_map.get(lg.signature_profile_id, f"Signature #{lg.signature_profile_id}"),
                "owner_name": own_name,
                "owner_id": lg.owner_user_id,
                "requester_name": req_name,
                "document_title": lg.document_title or (f"TSD #{lg.document_id}" if lg.document_id else "Document"),
                "status": status_eff,
                "otp_last2": lg.otp_last2 or "",
                "ip_address": lg.ip_address or "—",
                "created_at": lg.created_at.strftime("%Y-%m-%d %H:%M") if lg.created_at else "",
                "is_owner": lg.owner_user_id == actor.id,
            })
    except Exception:
        pass
    return render_template(
        "workspace/signatures.html",
        envelopes=envelopes,
        counts=counts,
        eligible_docs=eligible_docs,
        tenant_users=tenant_users,
        registered_signatures=registered_signatures,
        usage_logs=usage_logs,
        current_user_id=actor.id,
        current_user_email=getattr(actor, "email", "") or getattr(actor, "username", ""),
    )


@workspace_assets_views.route("/api/signatures/registered", methods=["GET"])
@login_required
def list_registered_signatures_api():
    """Return ONLY approved authorized staff signatures (metadata only; graphic released after OTP)."""
    from flask import jsonify
    from app.models.esignature import SignatureProfile
    from app.models.signature_governance import SignatureApprovalState, ensure_signature_governance_tables

    ensure_signature_governance_tables()
    actor = _actor()
    org_users = (
        User.query
        .filter(User.organization_id == actor.organization_id, User.is_active.is_(True))
        .all()
    )
    user_by_id = {u.id: u for u in org_users}
    org_user_ids = list(user_by_id.keys()) or [actor.id]
    rows = (
        SignatureProfile.query
        .filter(SignatureProfile.user_id.in_(org_user_ids))
        .order_by(SignatureProfile.is_default.desc(), SignatureProfile.created_at.desc())
        .limit(200)
        .all()
    )
    sig_ids = [r.id for r in rows]
    states = {}
    if sig_ids:
        for st in SignatureApprovalState.query.filter(SignatureApprovalState.signature_profile_id.in_(sig_ids)).all():
            states[st.signature_profile_id] = st

    items = []
    for sp in rows:
        st = states.get(sp.id)
        if not st or st.approval_status != "approved":
            continue
        u = user_by_id.get(sp.user_id)
        full = (u.get_full_name() or "").strip() if (u and hasattr(u, "get_full_name")) else ""
        items.append({
            "id": sp.id,
            "name": sp.name,
            "signature_type": sp.signature_type or "drawn",
            "capture_engine": st.capture_engine,
            "device_name": st.device_name or "",
            "initials_data": sp.initials_data or "",
            "is_default": bool(sp.is_default),
            "user_id": sp.user_id,
            "is_mine": sp.user_id == actor.id,
            "staff_name": full or (u.username if u else "") or (u.email if u else f"User #{sp.user_id}"),
            "staff_email": (u.email if u else "") or "",
            "created_at": sp.created_at.strftime("%Y-%m-%d %H:%M") if getattr(sp, "created_at", None) else "—",
            "requires_otp": True,
        })
    items.sort(key=lambda x: (not x["is_mine"], not x["is_default"], -x["id"]))
    return jsonify({"signatures": items})


@workspace_assets_views.route("/api/signatures/<int:sig_id>/request-otp", methods=["POST"])
@login_required
def request_signature_usage_otp(sig_id: int):
    """Log signature usage attempt, generate 6-digit OTP, and notify the signature owner."""
    from datetime import datetime, timedelta
    from flask import current_app, jsonify
    from app.models.esignature import SignatureProfile
    from app.models.signature_governance import (
        SignatureApprovalState,
        SignatureUsageLog,
        ensure_signature_governance_tables,
    )

    ensure_signature_governance_tables()
    actor = _actor()
    sp = db.session.get(SignatureProfile, sig_id)
    if not sp:
        return jsonify({"error": "Signature not found."}), 404
    owner = db.session.get(User, sp.user_id)
    if not owner or owner.organization_id != actor.organization_id:
        return jsonify({"error": "Unauthorized organization scope."}), 403

    st = SignatureApprovalState.query.filter_by(signature_profile_id=sp.id).first()
    if not st or st.approval_status != "approved":
        return jsonify({"error": "Only approved signatures can be applied. Please approve this signature in Brand & Assets → Signatures."}), 403

    payload = request.get_json(silent=True) or {}
    doc_id = payload.get("document_id")
    doc_title = str(payload.get("document_title") or "TSD Document").strip()[:240]

    otp_code = SignatureUsageLog.generate_otp()
    log = SignatureUsageLog(
        organization_id=actor.organization_id,
        signature_profile_id=sp.id,
        owner_user_id=owner.id,
        requester_user_id=actor.id,
        document_id=int(doc_id) if str(doc_id or "").isdigit() else None,
        document_title=doc_title,
        otp_code_hash=SignatureUsageLog.hash_otp(otp_code),
        otp_last2=otp_code[-2:],
        otp_expires_at=datetime.utcnow() + timedelta(minutes=5),
        status="otp_pending",
        ip_address=(request.headers.get("X-Forwarded-For") or request.remote_addr or "")[:64],
        user_agent=(request.headers.get("User-Agent") or "")[:255],
    )
    db.session.add(log)
    db.session.commit()

    # Notify signature owner via email if mail service is configured, and always log server-side
    owner_email = getattr(owner, "email", "") or ""
    req_name = (actor.get_full_name() or "").strip() if hasattr(actor, "get_full_name") else (getattr(actor, "email", "") or f"User #{actor.id}")
    notified_channel = "in-app security log"
    try:
        from app.extensions import mail
        from flask_mail import Message
        if mail and owner_email and current_app.config.get("MAIL_SERVER"):
            msg = Message(
                subject=f"[TrustSeal] Signature OTP Approval Required — {doc_title}",
                recipients=[owner_email],
                body=(
                    f"Authorized signature usage requested.\n\n"
                    f"Signature: {sp.name}\n"
                    f"Requested by: {req_name}\n"
                    f"Document: {doc_title}\n"
                    f"IP Address: {log.ip_address}\n\n"
                    f"One-Time Approval Code (OTP): {otp_code}\n"
                    f"Expires in 5 minutes. If you did not authorize this, deny it immediately in Brand & Assets → Signatures."
                ),
            )
            mail.send(msg)
            notified_channel = f"email ({owner_email}) & security log"
    except Exception:
        current_app.logger.info(
            "Signature OTP generated: log_id=%s owner=%s requester=%s doc=%s otp=%s",
            log.id, owner_email, req_name, doc_title, otp_code,
        )

    resp = {
        "usage_log_id": log.id,
        "owner_name": ((owner.get_full_name() or "").strip() if hasattr(owner, "get_full_name") else "") or owner_email,
        "owner_email_masked": (owner_email[:2] + "***@" + owner_email.split("@", 1)[1]) if "@" in owner_email else "owner",
        "notified_via": notified_channel,
        "expires_in_seconds": 300,
    }
    # In local/debug mode or when owner signs their own document, surface OTP hint so testing never deadlocks
    if current_app.debug or owner.id == actor.id:
        resp["dev_otp_code"] = otp_code
    return jsonify(resp), 201


@workspace_assets_views.route("/api/signatures/usage/<int:log_id>/verify-otp", methods=["POST"])
@login_required
def verify_signature_usage_otp(log_id: int):
    """Verify Owner OTP and release one platform-attested impression once."""
    from datetime import datetime
    from flask import jsonify
    from app.models.esignature import SignatureProfile
    from app.models.signature_governance import (
        SignatureApprovalState,
        SignatureUsageLog,
        ensure_signature_governance_tables,
    )

    ensure_signature_governance_tables()
    actor = _actor()
    log = db.session.get(SignatureUsageLog, log_id)
    if not log or log.organization_id != actor.organization_id:
        return jsonify({"error": "Usage request not found."}), 404
    if actor.id not in (log.requester_user_id, log.owner_user_id):
        return jsonify({"error": "Only the requester or signature owner can verify this OTP."}), 403
    if log.status == "denied":
        return jsonify({"error": "Signature usage was denied by the owner."}), 403
    if log.status == "applied":
        return jsonify({"error": "This OTP approval has already been used."}), 409
    if log.is_expired() and log.status != "approved":
        log.status = "expired"
        db.session.commit()
        return jsonify({"error": "OTP has expired. Please request a new OTP."}), 410

    payload = request.get_json(silent=True) or {}
    otp_input = str(payload.get("otp") or "").strip()
    if log.status != "approved":
        if not otp_input or not log.verify_otp(otp_input):
            return jsonify({"error": "Invalid OTP code. Please obtain the 6-digit approval code from the signature owner."}), 403

    sp = db.session.get(SignatureProfile, log.signature_profile_id)
    owner = db.session.get(User, log.owner_user_id)
    if not sp or not owner:
        return jsonify({"error": "Signature record missing."}), 404
    st = SignatureApprovalState.query.filter_by(signature_profile_id=sp.id).first()
    if not st or st.approval_status != "approved":
        return jsonify({"error": "This signature is no longer approved for use."}), 403

    now = datetime.utcnow()
    log.status = "applied"
    log.approved_at = log.approved_at or now
    log.applied_at = now
    db.session.commit()

    from app.services.signature_attestations import issue_signature_attestation
    attestation = issue_signature_attestation(
        organization_id=actor.organization_id,
        document_id=log.document_id,
        signature=sp,
        usage_log=log,
    )
    db.session.commit()  # persist a lazily provisioned tenant signing key

    from app.models.signature_governance import compute_ts_signature_seal, embed_ts_forensic_seal
    seal_hash, ts_fp = compute_ts_signature_seal(
        organization_id=actor.organization_id,
        signature_profile_id=sp.id,
        owner_user_id=sp.user_id,
        signature_data=sp.signature_data or "",
    )
    sealed_sig_data = embed_ts_forensic_seal(
        sp.signature_data or "",
        seal_hash=seal_hash,
        fingerprint=ts_fp,
        usage_log_id=log.id,
    )

    owner_name = ((owner.get_full_name() or "").strip() if hasattr(owner, "get_full_name") else "") or owner.email or f"User #{owner.id}"
    return jsonify({
        "usage_log_id": log.id,
        "signature_id": sp.id,
        "name": sp.name,
        "staff_name": owner_name,
        "signature_type": sp.signature_type,
        "signature_data": sealed_sig_data,
        "ts_fingerprint": ts_fp,
        "ts_seal_hash": seal_hash[:32],
        "ts_seal_engine": "TS-HMAC-SHA256-v1",
        "verified_at": now.strftime("%Y-%m-%d %H:%M UTC"),
        **attestation,
    })


@workspace_assets_views.route("/api/signatures/<int:sig_id>/system-verify", methods=["POST"])
@login_required
def system_verify_staff_signature(sig_id):
    """TrustSeal platform-only cryptographic integrity check for a registered signature.

    Never returns raw signature pixels; executes server-side HMAC-SHA256 verification
    and confirms approval state and vault integrity.
    """
    from app.models.esignature import SignatureProfile
    from app.models.signature_governance import (
        SignatureApprovalState,
        verify_ts_signature_integrity,
        ensure_signature_governance_tables,
    )

    ensure_signature_governance_tables()
    actor = _actor()
    sp = db.session.get(SignatureProfile, sig_id)
    if not sp:
        return jsonify({"verified": False, "error": "Signature not found."}), 404
    owner = db.session.get(User, sp.user_id)
    if not owner or owner.organization_id != actor.organization_id:
        return jsonify({"verified": False, "error": "Unauthorized organization scope."}), 403

    st = SignatureApprovalState.query.filter_by(signature_profile_id=sp.id).first()
    approval_status = st.approval_status if st else "pending"
    integrity = verify_ts_signature_integrity(
        organization_id=actor.organization_id,
        signature_profile_id=sp.id,
        owner_user_id=sp.user_id,
        signature_data=sp.signature_data or "",
    )
    return jsonify({
        "verified": bool(integrity.get("verified")),
        "signature_id": sp.id,
        "approval_status": approval_status,
        "fingerprint": integrity.get("fingerprint", ""),
        "engine": integrity.get("engine", "TS-HMAC-SHA256-v1"),
        "format": integrity.get("format", ""),
        "checked_at": integrity.get("verified_at", ""),
    })


@workspace_assets_views.route("/api/signatures/studio-meta", methods=["GET"])
@login_required
def api_signatures_studio_meta():
    from app.models.esignature import SignatureProfile
    from app.models.signature_governance import SignatureUsageLog, ensure_signature_governance_tables

    ensure_signature_governance_tables()
    actor = _actor()
    staff_rows = (
        User.query
        .filter(User.organization_id == actor.organization_id, User.is_active.is_(True))
        .order_by(User.email.asc())
        .limit(150)
        .all()
    )
    staff = []
    for u in staff_rows:
        full = ((u.get_full_name() or "").strip() if hasattr(u, "get_full_name") else "") or u.username or u.email or f"User #{u.id}"
        staff.append({"id": u.id, "name": full, "email": u.email or "", "is_me": (u.id == actor.id)})
    org_uids = [u.id for u in staff_rows] or [actor.id]
    sig_count = SignatureProfile.query.filter(SignatureProfile.user_id.in_(org_uids)).count()
    usage_count = SignatureUsageLog.query.filter_by(organization_id=actor.organization_id).count()
    return jsonify({
        "ok": True,
        "current_user_id": actor.id,
        "staff": staff,
        "counts": {"signatories": sig_count, "usage_logs": usage_count},
    })


@workspace_assets_views.route("/api/signatures/register-json", methods=["POST"])
@login_required
def api_register_staff_signature_json():
    from datetime import datetime
    from app.models.esignature import SignatureProfile
    from app.models.signature_governance import (
        SignatureApprovalState,
        SignatureUsageLog,
        compute_ts_signature_seal,
        embed_ts_forensic_seal,
        ensure_signature_governance_tables,
    )
    from app.services.signature_attestations import issue_signature_attestation

    ensure_signature_governance_tables()
    actor = _actor()
    body = request.get_json(silent=True) or {}
    staff_id = body.get("user_id") or actor.id
    try:
        staff_id = int(staff_id)
    except (TypeError, ValueError):
        staff_id = actor.id
    target_user = User.query.filter_by(id=staff_id, organization_id=actor.organization_id).first() or actor

    name = (body.get("name") or "").strip()[:100] or "Official Signature"
    sig_type = (body.get("signature_type") or "drawn").strip().lower()
    if sig_type not in ("drawn", "uploaded", "text"):
        sig_type = "drawn"
    capture_engine = (body.get("capture_engine") or "stylus_pen").strip().lower()
    if capture_engine not in ("device_pad", "stylus_pen", "ts_hq_engine", "uploaded"):
        capture_engine = "stylus_pen"
    device_name = (body.get("device_name") or "").strip()[:120]
    sig_data = (body.get("signature_data") or "").strip()
    initials = (body.get("initials_data") or "").strip()[:16]
    is_default = bool(body.get("is_default"))
    approve_now = bool(body.get("approve_now")) and (target_user.id == actor.id)
    apply_now = bool(body.get("apply_now")) and approve_now
    document_id = body.get("document_id")
    document_title = (body.get("document_title") or "TSD Document").strip()[:160]

    if not sig_data:
        return jsonify({"ok": False, "error": "Please capture, upload, or generate a signature first."}), 400

    if is_default:
        SignatureProfile.query.filter_by(user_id=target_user.id, is_default=True).update({"is_default": False})

    now = datetime.utcnow()
    sp = SignatureProfile(
        user_id=target_user.id,
        name=name,
        signature_type=sig_type,
        signature_data=sig_data,
        initials_data=initials or None,
        is_default=is_default or (SignatureProfile.query.filter_by(user_id=target_user.id).count() == 0),
    )
    db.session.add(sp)
    db.session.flush()

    st = SignatureApprovalState(
        organization_id=actor.organization_id,
        signature_profile_id=sp.id,
        approval_status="approved" if approve_now else "pending",
        capture_engine=capture_engine,
        device_name=device_name or None,
        approved_by_id=actor.id if approve_now else None,
        approved_at=now if approve_now else None,
    )
    db.session.add(st)
    db.session.commit()

    owner_name = ((target_user.get_full_name() or "").strip() if hasattr(target_user, "get_full_name") else "") or target_user.email or f"User #{target_user.id}"
    resp = {
        "ok": True,
        "signature_id": sp.id,
        "name": sp.name,
        "staff_name": owner_name,
        "approval_status": st.approval_status,
        "applied": False,
    }

    if apply_now:
        log = SignatureUsageLog(
            organization_id=actor.organization_id,
            signature_profile_id=sp.id,
            owner_user_id=target_user.id,
            requester_user_id=actor.id,
            document_id=int(document_id) if str(document_id or "").isdigit() else None,
            document_title=document_title,
            otp_code_hash="direct_owner_studio_capture",
            otp_last2="00",
            otp_expires_at=now,
            status="applied",
            approved_at=now,
            applied_at=now,
            ip_address=(request.headers.get("X-Forwarded-For") or request.remote_addr or "")[:64],
            user_agent=(request.headers.get("User-Agent") or "")[:255],
        )
        db.session.add(log)
        db.session.commit()

        attestation = issue_signature_attestation(
            organization_id=actor.organization_id,
            document_id=log.document_id,
            signature=sp,
            usage_log=log,
        )
        db.session.commit()

        seal_hash, ts_fp = compute_ts_signature_seal(
            organization_id=actor.organization_id,
            signature_profile_id=sp.id,
            owner_user_id=sp.user_id,
            signature_data=sp.signature_data or "",
        )
        sealed_sig_data = embed_ts_forensic_seal(
            sp.signature_data or "",
            seal_hash=seal_hash,
            fingerprint=ts_fp,
            usage_log_id=log.id,
        )
        resp.update({
            "applied": True,
            "usage_log_id": log.id,
            "signature_data": sealed_sig_data,
            "ts_fingerprint": ts_fp,
            "ts_seal_hash": seal_hash[:32],
            **attestation,
        })

    return jsonify(resp), 201


@workspace_assets_views.route("/signatures/register", methods=["POST"])
@login_required
def register_staff_signature():
    from datetime import datetime
    from app.models.esignature import SignatureProfile
    from app.models.signature_governance import SignatureApprovalState, ensure_signature_governance_tables

    ensure_signature_governance_tables()
    actor = _actor()
    staff_id = request.form.get("user_id", type=int) or actor.id
    target_user = User.query.filter_by(id=staff_id, organization_id=actor.organization_id).first()
    if not target_user:
        target_user = actor

    name = (request.form.get("name") or "").strip()[:100] or "Official Signature"
    sig_type = (request.form.get("signature_type") or "drawn").strip().lower()
    if sig_type not in ("drawn", "uploaded", "text"):
        sig_type = "drawn"
    capture_engine = (request.form.get("capture_engine") or "ts_hq_engine").strip().lower()
    if capture_engine not in ("device_pad", "stylus_pen", "ts_hq_engine", "uploaded"):
        capture_engine = "ts_hq_engine"
    device_name = (request.form.get("device_name") or "").strip()[:120]
    sig_data = (request.form.get("signature_data") or "").strip()
    initials = (request.form.get("initials_data") or "").strip()[:16]
    is_default = request.form.get("is_default") in ("1", "true", "on", "yes")
    approve_now = request.form.get("approve_now") in ("1", "true", "on", "yes") and (target_user.id == actor.id)

    if not sig_data:
        flash("Please capture, upload, or generate a signature before registering.", "warning")
        return redirect(url_for("workspace_assets_views.signatures_hub_page"))

    if is_default:
        SignatureProfile.query.filter_by(user_id=target_user.id, is_default=True).update({"is_default": False})

    sp = SignatureProfile(
        user_id=target_user.id,
        name=name,
        signature_type=sig_type,
        signature_data=sig_data,
        initials_data=initials or None,
        is_default=is_default or (SignatureProfile.query.filter_by(user_id=target_user.id).count() == 0),
    )
    db.session.add(sp)
    db.session.flush()

    st = SignatureApprovalState(
        organization_id=actor.organization_id,
        signature_profile_id=sp.id,
        approval_status="approved" if approve_now else "pending",
        capture_engine=capture_engine,
        device_name=device_name or None,
        approved_by_id=actor.id if approve_now else None,
        approved_at=datetime.utcnow() if approve_now else None,
    )
    db.session.add(st)
    db.session.commit()
    flash(
        f'Signatory "{name}" registered ({ "Approved & active" if approve_now else "Pending owner approval before use" }).',
        "success",
    )
    return redirect(url_for("workspace_assets_views.signatures_hub_page"))


@workspace_assets_views.route("/signatures/<int:sig_id>/approve", methods=["POST"])
@login_required
def approve_staff_signature(sig_id: int):
    from datetime import datetime
    from app.models.esignature import SignatureProfile
    from app.models.signature_governance import SignatureApprovalState, ensure_signature_governance_tables

    ensure_signature_governance_tables()
    actor = _actor()
    sp = db.session.get(SignatureProfile, sig_id)
    if not sp:
        abort(404)
    owner = db.session.get(User, sp.user_id)
    if not owner or owner.organization_id != actor.organization_id:
        abort(403)
    st = SignatureApprovalState.query.filter_by(signature_profile_id=sp.id).first()
    if not st:
        st = SignatureApprovalState(organization_id=actor.organization_id, signature_profile_id=sp.id)
        db.session.add(st)
    st.approval_status = "approved"
    st.approved_by_id = actor.id
    st.approved_at = datetime.utcnow()
    db.session.commit()
    flash(f'Signature "{sp.name}" approved for OTP-gated signing.', "success")
    return redirect(url_for("workspace_assets_views.signatures_hub_page"))


@workspace_assets_views.route("/signatures/<int:sig_id>/revoke", methods=["POST"])
@login_required
def revoke_staff_signature(sig_id: int):
    from app.models.esignature import SignatureProfile
    from app.models.signature_governance import SignatureApprovalState, ensure_signature_governance_tables

    ensure_signature_governance_tables()
    actor = _actor()
    sp = db.session.get(SignatureProfile, sig_id)
    if not sp:
        abort(404)
    owner = db.session.get(User, sp.user_id)
    if not owner or owner.organization_id != actor.organization_id:
        abort(403)
    st = SignatureApprovalState.query.filter_by(signature_profile_id=sp.id).first()
    if not st:
        st = SignatureApprovalState(organization_id=actor.organization_id, signature_profile_id=sp.id)
        db.session.add(st)
    st.approval_status = "revoked"
    db.session.commit()
    flash(f'Signature "{sp.name}" revoked and blocked from use.', "warning")
    return redirect(url_for("workspace_assets_views.signatures_hub_page"))


@workspace_assets_views.route("/signatures/usage/<int:log_id>/decision", methods=["POST"])
@login_required
def owner_decide_signature_usage(log_id: int):
    from datetime import datetime
    from app.models.signature_governance import SignatureUsageLog, ensure_signature_governance_tables

    ensure_signature_governance_tables()
    actor = _actor()
    log = db.session.get(SignatureUsageLog, log_id)
    if not log or log.organization_id != actor.organization_id:
        abort(404)
    if log.owner_user_id != actor.id:
        abort(403)
    decision = (request.form.get("decision") or "").strip().lower()
    if decision == "approve" and log.status == "otp_pending":
        log.status = "approved"
        log.approved_at = datetime.utcnow()
        db.session.commit()
        flash("Signature usage approved by owner.", "success")
    elif decision == "deny" and log.status in ("otp_pending", "approved"):
        log.status = "denied"
        db.session.commit()
        flash("Signature usage denied and blocked.", "warning")
    return redirect(url_for("workspace_assets_views.signatures_hub_page"))


@workspace_assets_views.route("/signatures/<int:sig_id>/default", methods=["POST"])
@login_required
def set_default_staff_signature(sig_id: int):
    from app.models.esignature import SignatureProfile

    actor = _actor()
    sp = db.session.get(SignatureProfile, sig_id)
    if not sp:
        abort(404)
    owner = db.session.get(User, sp.user_id)
    if not owner or owner.organization_id != actor.organization_id:
        abort(403)
    SignatureProfile.query.filter_by(user_id=sp.user_id, is_default=True).update({"is_default": False})
    sp.is_default = True
    db.session.commit()
    flash(f'"{sp.name}" set as default signature.', "success")
    return redirect(url_for("workspace_assets_views.signatures_hub_page"))


@workspace_assets_views.route("/signatures/<int:sig_id>/delete", methods=["POST"])
@login_required
def delete_staff_signature(sig_id: int):
    from app.models.esignature import SignatureProfile

    actor = _actor()
    sp = db.session.get(SignatureProfile, sig_id)
    if not sp:
        abort(404)
    owner = db.session.get(User, sp.user_id)
    if not owner or owner.organization_id != actor.organization_id:
        abort(403)
    db.session.delete(sp)
    db.session.commit()
    flash("Registered signature removed.", "success")
    return redirect(url_for("workspace_assets_views.signatures_hub_page"))


@workspace_assets_views.route("/signatures/create", methods=["POST"])
@login_required
def create_signature_request():
    from datetime import datetime
    from app.models.document import Document
    from app.models.document_blob import DocumentBlob
    from app.models.signing_envelope import EnvelopeParticipant, SigningEnvelope

    actor = _actor()
    doc_id = request.form.get("document_id", type=int)
    routing_mode = (request.form.get("routing_mode") or "sequential").strip().lower()
    if routing_mode not in ("sequential", "parallel"):
        routing_mode = "sequential"
    signer_ids = request.form.getlist("signer_ids", type=int)

    if not doc_id:
        flash("Select a document to create a signature request.", "error")
        return redirect(url_for("workspace_assets_views.signatures_hub_page"))

    doc = Document.query.filter_by(
        id=doc_id, organization_id=actor.organization_id, deleted_at=None
    ).first()
    if doc is None:
        flash("Document not found.", "error")
        return redirect(url_for("workspace_assets_views.signatures_hub_page"))

    blob = (
        DocumentBlob.query
        .filter_by(document_id=doc.id)
        .order_by(DocumentBlob.id.desc())
        .first()
    )
    if blob is None:
        flash("Document has no stored PDF revision.", "error")
        return redirect(url_for("workspace_assets_views.signatures_hub_page"))

    env = SigningEnvelope(
        document_id=doc.id,
        document_blob_id=blob.id,
        document_sha256=blob.sha256,
        organization_id=actor.organization_id,
        created_by_id=actor.id,
        state="draft",
        routing_mode=routing_mode,
    )
    db.session.add(env)
    db.session.flush()

    valid_users = (
        User.query
        .filter(User.organization_id == actor.organization_id, User.id.in_(signer_ids))
        .all()
    ) if signer_ids else []
    order = 1
    seen = set()
    for uid in signer_ids:
        if uid in seen or not any(u.id == uid for u in valid_users):
            continue
        seen.add(uid)
        db.session.add(EnvelopeParticipant(
            envelope_id=env.id,
            user_id=uid,
            signing_order=order,
            role="signer",
        ))
        order += 1

    if request.form.get("send_now") == "1" and order > 1:
        env.state = "prepared"
        env.prepared_at = datetime.utcnow()

    db.session.commit()
    flash(f'Signature request #{env.id} created ({env.state}).', "success")
    return redirect(url_for("workspace_assets_views.signatures_hub_page"))


@workspace_assets_views.route("/signatures/<int:env_id>/prepare", methods=["POST"])
@login_required
def prepare_signature_request(env_id: int):
    from datetime import datetime
    from app.models.signing_envelope import EnvelopeParticipant, SigningEnvelope

    actor = _actor()
    env = SigningEnvelope.query.filter_by(id=env_id, organization_id=actor.organization_id).first()
    if env is None:
        abort(404)
    if env.state != "draft":
        flash("Only draft envelopes can be prepared.", "error")
        return redirect(url_for("workspace_assets_views.signatures_hub_page"))
    if EnvelopeParticipant.query.filter_by(envelope_id=env.id).count() == 0:
        flash("Add at least one signer before preparing.", "error")
        return redirect(url_for("workspace_assets_views.signatures_hub_page"))
    env.state = "prepared"
    env.prepared_at = datetime.utcnow()
    db.session.commit()
    flash(f"Envelope #{env.id} prepared for signing.", "success")
    return redirect(url_for("workspace_assets_views.signatures_hub_page"))


@workspace_assets_views.route("/signatures/<int:env_id>/cancel", methods=["POST"])
@login_required
def cancel_signature_request(env_id: int):
    from datetime import datetime
    from app.models.signing_envelope import SigningEnvelope

    actor = _actor()
    env = SigningEnvelope.query.filter_by(id=env_id, organization_id=actor.organization_id).first()
    if env is None:
        abort(404)
    if env.state == "draft":
        env.state = "cancelled"
        env.cancelled_at = datetime.utcnow()
    elif env.state == "prepared":
        env.state = "withdrawn"
        env.withdrawn_at = datetime.utcnow()
        env.withdrawn_by_id = actor.id
        env.withdraw_reason = "Withdrawn by workspace operator"
    db.session.commit()
    flash(f"Envelope #{env.id} marked as {env.state}.", "success")
    return redirect(url_for("workspace_assets_views.signatures_hub_page"))
