from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user

from app.blueprints.system import system_bp

main_views = Blueprint('main_views', __name__)


@main_views.route('/')
def home():
    """Root route.

    Authenticated users land on the full-width Workspace Overview populated with
    live documents, contracts, projects, brand/signing assets, and recent activity.
    """
    if not current_user.is_authenticated:
        return render_template("public/landing.html")

    org_id = getattr(current_user, "organization_id", None)
    recent_documents = []
    recent_contracts = []
    active_projects = []
    metrics = {
        "docs_total": 0,
        "contracts_total": 0,
        "contracts_signed": 0,
        "projects_total": 0,
        "stamps_total": 0,
        "letterheads_total": 0,
        "signatures_total": 0,
        "templates_total": 3325,
    }
    try:
        from app.models.tsd_document import TSDocument
        from app.models.user import User

        doc_q = TSDocument.query.filter_by(organization_id=org_id, deleted_at=None) if hasattr(TSDocument, "deleted_at") else TSDocument.query.filter_by(organization_id=org_id)
        metrics["docs_total"] = doc_q.count()
        for d in doc_q.order_by(TSDocument.updated_at.desc()).limit(8).all():
            uid = getattr(d, "created_by_id", None) or getattr(d, "owner_id", None)
            owner = User.query.get(uid) if uid else None
            owner_name = ((owner.get_full_name() or "").strip() if (owner and hasattr(owner, "get_full_name")) else "") or (owner.email if owner else "—")
            recent_documents.append({
                "id": d.id,
                "title": d.title or f"Document #{d.id}",
                "reference": f"TSD-{d.id:05d}",
                "status": (getattr(d, "status", None) or "draft").lower(),
                "version": getattr(d, "version", 1) or 1,
                "owner_name": owner_name,
                "updated_label": d.updated_at.strftime("%Y-%m-%d %H:%M") if getattr(d, "updated_at", None) else "—",
                "url": f"/documents/library/{d.id}",
            })
    except Exception:
        pass

    try:
        from app.models.tsd_stamp import TSDStamp
        from app.models.tsd_letterhead import TSDLetterhead
        from app.models.esignature import SignatureProfile
        from app.models.user import User

        metrics["stamps_total"] = TSDStamp.query.filter_by(organization_id=org_id).count()
        metrics["letterheads_total"] = TSDLetterhead.query.filter_by(organization_id=org_id).count()
        org_uids = [u.id for u in User.query.filter_by(organization_id=org_id, is_active=True).all()] or [current_user.id]
        metrics["signatures_total"] = SignatureProfile.query.filter(SignatureProfile.user_id.in_(org_uids)).count()
    except Exception:
        pass

    try:
        from app.models.contract_workflow import ContractDeliverable, ContractWorkflow, Project
        from app.blueprints.contracts.lifecycle_service import compute_deliverable_progress

        wfs = ContractWorkflow.query.filter_by(organization_id=org_id).order_by(ContractWorkflow.updated_at.desc()).all()
        metrics["contracts_total"] = len(wfs)
        metrics["contracts_signed"] = sum(1 for w in wfs if w.canonical_status() == "SIGNED")
        for w in wfs[:6]:
            recent_contracts.append({
                "document_id": w.document_id,
                "contract_number": w.contract_number or f"CTR-{w.document_id}",
                "title": getattr(w, "title", None) or (w.document.title if getattr(w, "document", None) else f"Contract #{w.document_id}"),
                "counterparty": getattr(w, "counterparty_name", None) or "—",
                "status": w.canonical_status(),
                "stage": getattr(w, "stage_label", None) or getattr(w, "stage", "draft"),
                "deal_value": getattr(w, "deal_value", None) or "—",
                "url": f"/contracts/{w.document_id}/workflow",
            })

        projs = Project.query.filter_by(organization_id=org_id).order_by(Project.is_default.desc(), Project.updated_at.desc()).all()
        metrics["projects_total"] = len(projs)
        delivs = ContractDeliverable.query.filter_by(organization_id=org_id).all()
        deliv_by_wf = {}
        for dl in delivs:
            deliv_by_wf.setdefault(dl.contract_id, []).append(dl)
        for p in projs[:5]:
            p_wfs = [w for w in wfs if w.project_id == p.id]
            p_dl = [dl for w in p_wfs for dl in deliv_by_wf.get(w.id, [])]
            prog = compute_deliverable_progress(p_dl)
            active_projects.append({
                "id": p.id,
                "code": p.project_code,
                "name": p.name,
                "status": p.status,
                "contracts_total": len(p_wfs),
                "deliverables_pct": prog["pct"],
                "url": f"/projects/{p.id}",
            })
    except Exception:
        pass

    return render_template(
        "dashboard.html",
        metrics=metrics,
        recent_documents=recent_documents,
        recent_contracts=recent_contracts,
        active_projects=active_projects,
    )


@main_views.route('/welcome')
def welcome():
    """Public landing — always rendered regardless of auth state."""
    return render_template("public/landing.html")


@main_views.route('/trust')
def trust():
    """Public Trust & Security page.

    Canonical statement of what TRUSTSEAL cryptographically proves,
    what it records as workflow evidence, and what it does not claim.
    Linked from the landing hero, every error page and the signer
    footer, so the page must stay public (no auth gating).
    """
    return render_template("public/trust.html")


@main_views.route('/pricing')
def pricing():
    """Public pricing page — honest contact-based quote flow."""
    return render_template("public/pricing.html")
