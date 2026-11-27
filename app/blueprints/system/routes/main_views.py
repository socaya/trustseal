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
    return render_template("public/landing.html", public_nav="home")


PUBLIC_MODULES = [
    {
        "slug": "projects",
        "num": "01",
        "category": "Delivery & Portfolio Management",
        "name": "Project Management Studio",
        "short": "Portfolios, WBS, CPM Gantt, resources, weekly timesheets, expenses & EVM",
        "spec": "WBS · CPM Gantt · Timesheets · EVM",
        "summary": (
            "Govern portfolios, programmes, and scored demand intake from charter approval "
            "to project closure with explainable 6-dimension RAG health scoring and live "
            "contract financial rollups."
        ),
        "cta_label": "Open Project Studio",
        "cta_href": "/projects",
        "capabilities": [
            ("WBS, DAG Dependencies & CPM Gantt", "Cycle-protected task dependencies with deterministic critical-path scheduling, milestones, and baseline variance tracking."),
            ("Resources, Capacity & Equipment", "Centralized resource directory, capacity allocation, equipment bookings, agile sprints, and backlog management."),
            ("Weekly Timesheets & Personal Expenses", "Role-separated approvals posting directly to the project cost ledger, Earned Value Management (EVM), and budget baselines."),
            ("Procurement, RAID, HSE & Client Portals", "End-to-end vendor tenders, risk and change registers, compliance logs, M&E indicators, and token-scoped client portals."),
        ],
        "connections": [
            ("Contracts Lifecycle", "/platform/contracts", "Linked contracts feed obligations, addendums/NCEs, and real-time spend into project budgets."),
            ("TSD Document Vault", "/platform/documents", "Charters, SOWs, and delivery reports stay encrypted and revision-controlled inside the workspace."),
            ("Governance & Mobile", "/platform/governance", "Approve timesheets and monitor project progress on iOS & Android with full audit trails."),
        ],
    },
    {
        "slug": "contracts",
        "num": "02",
        "category": "Commercial & Legal Control",
        "name": "Contracts Lifecycle (CLM)",
        "short": "3,325+ templates, redlines, addendums/NCEs, obligations & live burn rate",
        "spec": "Addendums · NCEs · Spend · Burn",
        "summary": (
            "Draft, negotiate, execute, and govern every commercial agreement from one "
            "authoritative register — grouping primary contracts with their addendums, "
            "No-Cost Extensions (NCEs), obligations, and monthly burn rates."
        ),
        "cta_label": "Open Contracts Hub",
        "cta_href": "/contracts/signed",
        "capabilities": [
            ("3,325+ Full-Length Contract Blueprints", "Instantiate MSAs, SOWs, NDAs, employment agreements, and sector policies with automated redline diff comparison."),
            ("Parent-Child Addendums & NCEs", "Track amendments, renewals, and No-Cost Extensions directly beneath each master agreement with complete version lineage."),
            ("Obligations & Deliverable Acceptance", "Monitor milestones, probation reviews, SLA commitments, and formal counterparty deliverable sign-offs."),
            ("Live Contract Spend & Burn Rate", "Real-time commitment ledgers and monthly burn-rate tracking synchronized directly with Project Management Studio."),
        ],
        "connections": [
            ("eIDAS 2.0 eSignature", "/platform/esignature", "Route finalized contracts for SES, AES, or QES signing and PAdES-B-LTA archival sealing."),
            ("Project Management Studio", "/platform/projects", "Roll contract values, deliverables, and actual spend automatically into project health."),
            ("Corporate Stamps & Brand", "/platform/stamps", "Apply official letterheads and custodian-gated corporate seals directly before execution."),
        ],
    },
    {
        "slug": "esignature",
        "num": "03",
        "category": "Native eIDAS 2.0 Electronic Signatures",
        "name": "eIDAS 2.0 Send for eSignature",
        "short": "Sequential/parallel routing, CSV bulk invites, SES/AES/QES, CSC v2 & EUDI Wallet",
        "spec": "SES · AES · QES · CSC v2 · EUDI Wallet",
        "summary": (
            "Implemented 100% natively inside TRUSTSEAL with zero third-party signing lock-in. "
            "Send single agreements, shareable kiosk links, or 250-recipient CSV bulk batches "
            "under Simple (SES), Advanced (AES), or Qualified (QES) assurance."
        ),
        "cta_label": "Open Send for eSignature Studio",
        "cta_href": "/esignatures/send",
        "capabilities": [
            ("Multi-Recipient Routing & Fillable Fields", "Sequential, parallel, and quorum routing with Signer, Approver, Witness, and CC roles plus interactive signature, date, text, and stamp fields."),
            ("CSV Bulk Invites, Reminders & Expiry", "Dispatch individualized trackable signing packages at scale with 1–180 day expiration limits, automated follow-ups, decline, and reassignment."),
            ("Remote QSCD (CSC API v2) & EUDI Wallet", "Execute EU Qualified Electronic Signatures using SCAL2 SAD sole-control authorization or EUDI Wallet ARF OpenID4VP LoA-High identity presentation."),
            ("ETSI PAdES-B-LTA & Completion Certificate", "Seal finalized artifacts with RFC 3161 timestamps, embedded OCSP/CRL revocation data, and an immutable SHA-256 hash-chained Certificate of Completion."),
        ],
        "connections": [
            ("Trust & eIDAS 2.0 Standards", "/trust", "Review full Regulation (EU) 2024/1183, ETSI EN 319 142, and QCStatements specifications."),
            ("Public Verifier", "/verify", "Verify any ESIG package reference, document SHA-256, or sealed PAdES PDF independently."),
            ("Contracts Lifecycle", "/platform/contracts", "Send negotiated agreements straight from CLM without downloading or re-uploading files."),
        ],
    },
    {
        "slug": "documents",
        "num": "04",
        "category": "Encrypted Authoring & Storage",
        "name": "TSD Encrypted Document Vault",
        "short": "Fernet-encrypted .tsd containers, revision snapshots & export enforcement",
        "spec": "Fernet .tsd · Versioning · Export Rules",
        "summary": (
            "Author policies, board packs, and legal agreements inside a dedicated document "
            "studio backed by per-tenant Fernet-encrypted .tsd containers, optimistic version "
            "locking, and enforceable export policies."
        ),
        "cta_label": "Open Document Library",
        "cta_href": "/documents/library",
        "capabilities": [
            ("Per-Tenant Encrypted .tsd Containers", "Authenticated encryption protects every stored document with verifiable SHA-256 integrity digests."),
            ("Enforceable Export Policies", "Restrict confidential records to Encrypted Only or permit controlled PDF export for external review and signing."),
            ("Multi-Format Document Ingestion", "Import DOCX, PDF, XLSX, HTML, and Markdown files cleanly into governed, searchable workspace records."),
            ("Token-Scoped External Sharing", "Share time-limited review links with counterparties while logging every open, view, and revision."),
        ],
        "connections": [
            ("Corporate Stamps & Brand", "/platform/stamps", "Attach approved organization letterheads and official stamps directly inside the editor."),
            ("eIDAS 2.0 eSignature", "/platform/esignature", "Dispatch any .tsd document directly into an SES, AES, or QES signing workflow."),
            ("Governance & Mobile", "/platform/governance", "Search and inspect .tsd records and version metadata directly from TRUSTSEAL Mobile."),
        ],
    },
    {
        "slug": "stamps",
        "num": "05",
        "category": "Corporate Identity & Forensics",
        "name": "Corporate Stamps & Brand Studio",
        "short": "Custodian-gated corporate e-stamps, official letterheads & forensic receipts",
        "spec": "PAdES-B-LTA · RFC 3161 · Forensics",
        "summary": (
            "Standardize every official outbound document with authorized corporate e-stamps, "
            "dated approval seals, verified letterheads, OTP-protected executive signatures, "
            "and covert forensic stamp receipts."
        ),
        "cta_label": "Open Stamp Studio",
        "cta_href": "/stamps",
        "capabilities": [
            ("Custodian-Gated Corporate Stamp Studio", "Design and govern round, dated, and departmental seals strictly under authorized custodian permissions."),
            ("Official Letterheads & Media Library", "Maintain approved corporate stationery presets and brand assets applied cleanly across documents and contracts."),
            ("Covert Forensic Stamp Receipts", "Embed cryptographic receipt nonces and QR verification endpoints so counterparties can validate genuine impressions."),
            ("OTP-Protected Signatory Vault", "Require 6-digit owner OTP confirmation before any registered executive signature is applied to a document."),
        ],
        "connections": [
            ("Public Verifier", "/verify", "Validate stamp receipts and sealed PDFs with zero account required."),
            ("TSD Document Vault", "/platform/documents", "Apply official letterheads and seals natively during document authoring."),
            ("Contracts Lifecycle", "/platform/contracts", "Enforce mandatory corporate stamp gates prior to contract execution."),
        ],
    },
    {
        "slug": "governance",
        "num": "06",
        "category": "Security, Compliance & Mobility",
        "name": "Governance, Audit & Mobile App",
        "short": "PostgreSQL RLS, SAML 2.0 SSO, SCIM, 7-year retention & Flutter Mobile App",
        "spec": "RLS · SAML SSO · 7-Year Vault · Flutter",
        "summary": (
            "Built for regulated enterprises requiring database-enforced tenant isolation, "
            "immutable hash-chained audit logs, 7-year evidence preservation, and native "
            "iOS & Android mobile access."
        ),
        "cta_label": "Review Trust & Security",
        "cta_href": "/trust",
        "capabilities": [
            ("PostgreSQL RLS, SAML 2.0 & SCIM", "Enforce multi-tenant isolation at the database layer alongside enterprise SSO, MFA step-up, and directory sync."),
            ("Immutable SHA-256 Hash-Chained Audit Log", "Every approval, stage gate, stamp, and signature links cryptographically to detect any retrospective alteration."),
            ("7-Year Evidence Retention & Legal Holds", "Retain validation dossiers, RFC 3161 TSA tokens, and OCSP/CRL snapshots for regulatory and court audits."),
            ("Native Flutter Mobile App (iOS & Android)", "Track projects, submit timesheets, dispatch eIDAS 2.0 signatures, inspect documents, and verify evidence on mobile."),
        ],
        "connections": [
            ("Trust & eIDAS 2.0 Standards", "/trust", "Inspect full cryptographic architecture, RFC 3161 timestamping, and OCSP/CRL retention."),
            ("How It Works", "/how-it-works", "See how governance anchors every stage from project intake to public verification."),
            ("Pricing", "/pricing", "Explore enterprise deployment, dedicated QTSP configuration, and support options."),
        ],
    },
]
PUBLIC_MODULES_BY_SLUG = {m["slug"]: m for m in PUBLIC_MODULES}


@main_views.route('/platform')
def platform():
    """Dedicated Platform Suite index page linking to each module's own page."""
    return render_template("public/platform.html", modules=PUBLIC_MODULES, public_nav="platform")


@main_views.route('/platform/<slug>')
def platform_module(slug: str):
    """Dedicated full-screen page for an individual TRUSTSEAL module."""
    mod = PUBLIC_MODULES_BY_SLUG.get(slug)
    if not mod:
        from flask import abort
        abort(404)
    idx = next(i for i, m in enumerate(PUBLIC_MODULES) if m["slug"] == slug)
    prev_mod = PUBLIC_MODULES[idx - 1] if idx > 0 else None
    next_mod = PUBLIC_MODULES[idx + 1] if idx + 1 < len(PUBLIC_MODULES) else None
    active = "esignature" if slug == "esignature" else "platform"
    return render_template(
        "public/module_detail.html",
        module=mod,
        modules=PUBLIC_MODULES,
        prev_mod=prev_mod,
        next_mod=next_mod,
        public_nav=active,
    )


@main_views.route('/how-it-works')
def how_it_works():
    """Dedicated End-to-End Connected Lifecycle page."""
    return render_template("public/how_it_works.html", modules=PUBLIC_MODULES, public_nav="how_it_works")


@main_views.route('/trust')
def trust():
    """Public Trust, Security & eIDAS 2.0 Standards page."""
    return render_template("public/trust.html", public_nav="trust")


@main_views.route('/pricing')
def pricing():
    """Public pricing page — honest contact-based quote flow."""
    return render_template("public/pricing.html", public_nav="pricing")
