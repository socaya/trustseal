"""Contract Lifecycle Management (CLM) service layer.

Orchestrates:
- Default Project & Contract Templates seeding per tenant
- Canonical status transitions: DRAFT, SIGNED, SUSPENDED, TERMINATED
- Suspension timer-pause & Resumption timer-resume on Deliverables
- First-class Probation Period confirmation, extension, and termination
- Template instantiation with merge fields + auto-seeded Key Terms & Deliverables
- Atomic Deal Closing: TSD freeze + TSDStampInsertion receipt + EvidenceRetention
- Version diffing between TSDocumentVersion snapshots
- Chained-hash SecurityEvent & OutboxEvent emission
"""
from __future__ import annotations

import difflib
import hashlib
import html as html_std
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.extensions import db
from app.models.contract_workflow import (
    CONTRACT_STATUS_LABELS,
    ContractDeliverable,
    ContractKeyTerm,
    ContractTemplate,
    ContractWorkflow,
    LOCKED_STAGES,
    Project,
    STAGE_LABELS,
    ensure_contract_workflow_table,
)
from app.models.event_delivery import OutboxEvent, SecurityEvent
from app.models.evidence_preservation import EvidenceLegalHold, EvidenceRetention
from app.models.tsd_document import TSDocument
from app.models.tsd_document_version import TSDocumentVersion
from app.services.tsd_format import (
    decrypt_content_envelope,
    encrypt_content_envelope,
    pack_content,
    sanitize_html,
    sha256_hex,
)
from app.services.tsd_pdf import render_html_to_pdf


def actor_label(actor) -> str:
    full = (actor.get_full_name() or "").strip() if hasattr(actor, "get_full_name") else ""
    return full or getattr(actor, "username", None) or getattr(actor, "email", None) or f"User #{actor.id}"


def normalize_stage(raw_status: str | None) -> str:
    s = (raw_status or "draft").strip().lower().replace("-", "_").replace(" ", "_")
    if s in ("finalized", "signed", "completed", "executed", "active", "prepared"):
        return "signed"
    if s in ("suspended", "paused", "on_hold"):
        return "suspended"
    if s in ("pending_signature", "awaiting_signature", "sent", "in_progress", "out_for_signature", "signature"):
        return "signature"
    if s in ("pending_approval", "approval", "awaiting_approval"):
        return "approval"
    if s in ("negotiation", "counterparty_review", "external_review"):
        return "negotiation"
    if s in ("pending_review", "in_review", "review", "redline"):
        return "review"
    if s in ("expired", "terminated"):
        return "expired"
    if s in ("void", "voided", "declined", "cancelled", "canceled", "archived", "closed"):
        return "closed"
    return "draft"


def stage_to_canonical_status(stage: str) -> str:
    if stage == "signed":
        return "SIGNED"
    if stage == "suspended":
        return "SUSPENDED"
    if stage in ("expired", "closed"):
        return "TERMINATED"
    return "DRAFT"


def emit_contract_security_event(
    *,
    organization_id: int,
    actor_id: int,
    action: str,
    document_id: int,
    outcome: str = "success",
) -> None:
    db.session.add(
        SecurityEvent(
            organization_id=organization_id,
            actor_id=actor_id,
            action=action,
            resource_type="contract",
            resource_id=document_id,
            outcome=outcome[:24],
            correlation_id=uuid.uuid4().hex,
        )
    )


def emit_contract_outbox(
    *,
    organization_id: int,
    event_type: str,
    document_id: int,
    payload: dict[str, Any],
) -> None:
    db.session.add(
        OutboxEvent(
            event_type=event_type,
            aggregate_type="contract",
            aggregate_id=document_id,
            organization_id=organization_id,
            payload=payload,
            idempotency_key=f"{event_type}:{organization_id}:{document_id}:{uuid.uuid4().hex[:12]}",
            state="pending",
        )
    )


def append_workflow_event(wf: ContractWorkflow, actor, action: str, detail: str = "") -> None:
    events = list(wf.events_json or [])
    events.insert(
        0,
        {
            "at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            "actor": actor_label(actor),
            "action": action,
            "detail": detail,
        },
    )
    wf.events_json = events[:100]
    flag_modified(wf, "events_json")


def ensure_default_project(organization_id: int, actor=None) -> Project:
    """Ensure the tenant always has a default Project so every Contract has a project_id."""
    ensure_contract_workflow_table()
    proj = Project.query.filter_by(organization_id=organization_id, is_default=True).first()
    if proj is None:
        proj = Project.query.filter_by(organization_id=organization_id).order_by(Project.id.asc()).first()
    if proj is None:
        proj = Project(
            organization_id=organization_id,
            project_code=f"PRJ-{datetime.utcnow().year}-001",
            name="General Operations",
            description="Default workspace project for contracts not assigned to a specific client or delivery engagement.",
            category="internal_ops",
            owner_user_id=getattr(actor, "id", None),
            status="active",
            currency="USD",
            is_default=True,
        )
        db.session.add(proj)
        db.session.flush()
    return proj


_SYSTEM_TEMPLATES = [
    {
        "name": "Project Statement of Work (SOW)",
        "description": "Milestone-driven project delivery contract with weighted deliverables and payment tranches.",
        "contract_type": "sow",
        "default_project_category": "client_delivery",
        "body_html": (
            "<h1>STATEMENT OF WORK (SOW)</h1>"
            "<p>This Statement of Work governs delivery under Project <strong>{{project_name}}</strong> ({{project_code}}) "
            "between the Organization and <strong>{{counterparty_name}}</strong>, effective <strong>{{effective_date}}</strong>.</p>"
            "<h2>1. Scope &amp; Deliverables</h2><p>Provider shall deliver all milestones listed in the Contract Deliverables Schedule.</p>"
            "<h2>2. Fees &amp; Payment Schedule</h2><p>Total contract value is <strong>{{currency}} {{deal_value}}</strong>, payable upon milestone acceptance within 30 calendar days.</p>"
            "<h2>3. Acceptance &amp; Warranty</h2><p>Client has 10 business days to accept or issue written rejection notes for each submitted deliverable.</p>"
            "<h2>4. Governing Law</h2><p>This SOW is governed by the laws of <strong>{{governing_law}}</strong>.</p>"
        ),
        "variables_json": [
            {"key": "counterparty_name", "label": "Client / Counterparty", "type": "text", "required": True},
            {"key": "deal_value", "label": "Contract Value", "type": "text", "required": False},
            {"key": "effective_date", "label": "Effective Date", "type": "date", "required": False},
            {"key": "governing_law", "label": "Governing Law", "type": "text", "required": False, "default": "Kenya"},
        ],
        "default_key_terms_json": [
            {"category": "financial", "term_key": "payment_terms", "label": "Payment Terms", "value_text": "Net 30 days from milestone acceptance", "clause_ref": "2. Fees & Payment Schedule"},
            {"category": "sla", "term_key": "acceptance_window", "label": "Deliverable Acceptance Window", "value_text": "10 business days", "numeric_value": 10, "unit": "days", "clause_ref": "3. Acceptance & Warranty"},
            {"category": "schedule", "term_key": "warranty_period", "label": "Defect Liability / Warranty", "value_text": "90 days post go-live", "numeric_value": 90, "unit": "days", "clause_ref": "3. Acceptance & Warranty"},
        ],
        "default_deliverables_json": [
            {"title": "Project Kickoff & Architecture Sign-off", "deliverable_type": "milestone", "project_phase": "Phase 1: Discovery", "offset_days": 14, "weight_pct": 25},
            {"title": "Core Implementation & UAT Build", "deliverable_type": "milestone", "project_phase": "Phase 2: Build", "offset_days": 45, "weight_pct": 45},
            {"title": "Production Go-Live & Final Acceptance", "deliverable_type": "acceptance_gate", "project_phase": "Phase 3: Handover", "offset_days": 75, "weight_pct": 30},
        ],
    },
    {
        "name": "Employment Contract (90-Day Probation)",
        "description": "Standard employment contract with structured 90-day probation period, 30/60/90-day review milestones, and confirmation controls.",
        "contract_type": "employment_probation",
        "default_project_category": "hr_onboarding",
        "body_html": (
            "<h1>EMPLOYMENT AGREEMENT (WITH PROBATION PERIOD)</h1>"
            "<p>This Employment Agreement is entered into under Project / Cohort <strong>{{project_name}}</strong> "
            "between the Organization and <strong>{{counterparty_name}}</strong>, commencing on <strong>{{effective_date}}</strong>.</p>"
            "<h2>1. Probationary Period</h2><p>The first <strong>90 calendar days</strong> of employment (ending <strong>{{probation_end_date}}</strong>) constitute a Probationary Period. Performance will be evaluated at 30, 60, and 80 days.</p>"
            "<h2>2. Compensation &amp; Benefits</h2><p>Annual / monthly remuneration is <strong>{{currency}} {{deal_value}}</strong>, subject to statutory deductions.</p>"
            "<h2>3. Notice Period &amp; Termination</h2><p>During probation, either party may terminate with 7 days written notice. Upon confirmation, 30 days written notice applies.</p>"
            "<h2>4. Confidentiality &amp; IP</h2><p>All work product created during employment is assigned to the Organization.</p>"
        ),
        "variables_json": [
            {"key": "counterparty_name", "label": "Employee Full Name", "type": "text", "required": True},
            {"key": "deal_value", "label": "Compensation", "type": "text", "required": False},
            {"key": "effective_date", "label": "Start Date", "type": "date", "required": False},
            {"key": "probation_days", "label": "Probation Duration (Days)", "type": "number", "default": "90"},
        ],
        "default_key_terms_json": [
            {"category": "probation", "term_key": "probation_period", "label": "Probation Period", "value_text": "90 calendar days probation", "numeric_value": 90, "unit": "days", "offset_days": 90, "alert_days_before": 14, "clause_ref": "1. Probationary Period"},
            {"category": "renewal_notice", "term_key": "probation_notice", "label": "Notice During Probation", "value_text": "7 days written notice", "numeric_value": 7, "unit": "days", "clause_ref": "3. Notice Period & Termination"},
            {"category": "renewal_notice", "term_key": "post_probation_notice", "label": "Post-Confirmation Notice", "value_text": "30 days written notice", "numeric_value": 30, "unit": "days", "clause_ref": "3. Notice Period & Termination"},
        ],
        "default_deliverables_json": [
            {"title": "30-Day Onboarding & Initial Check-In", "deliverable_type": "probation_review", "project_phase": "Probation", "offset_days": 30, "weight_pct": 25},
            {"title": "60-Day Mid-Probation Performance Review", "deliverable_type": "probation_review", "project_phase": "Probation", "offset_days": 60, "weight_pct": 35},
            {"title": "Final Probation Assessment & Confirmation Decision", "deliverable_type": "probation_review", "project_phase": "Probation", "offset_days": 80, "weight_pct": 40},
        ],
    },
    {
        "name": "Master Service Agreement (MSA)",
        "description": "Umbrella commercial services agreement with liability cap, SLA, and auto-renewal notice tracking.",
        "contract_type": "msa",
        "default_project_category": "client_delivery",
        "body_html": (
            "<h1>MASTER SERVICE AGREEMENT</h1>"
            "<p>This Master Service Agreement is executed under Project <strong>{{project_name}}</strong> "
            "between the Organization and <strong>{{counterparty_name}}</strong>, effective <strong>{{effective_date}}</strong>.</p>"
            "<h2>1. Services &amp; SOWs</h2><p>Services shall be specified in individual Statements of Work referencing this MSA.</p>"
            "<h2>2. Limitation of Liability</h2><p>Aggregate liability is capped at 12 months of fees paid under the relevant SOW.</p>"
            "<h2>3. Term &amp; Renewal</h2><p>Initial term of 12 months with 30 days prior written notice required to opt out of renewal.</p>"
        ),
        "variables_json": [
            {"key": "counterparty_name", "label": "Counterparty Legal Name", "type": "text", "required": True},
            {"key": "deal_value", "label": "Estimated Annual Value", "type": "text", "required": False},
            {"key": "effective_date", "label": "Effective Date", "type": "date", "required": False},
            {"key": "governing_law", "label": "Governing Law", "type": "text", "default": "England & Wales"},
        ],
        "default_key_terms_json": [
            {"category": "liability_ip", "term_key": "liability_cap", "label": "Liability Cap", "value_text": "12 months trailing fees", "clause_ref": "2. Limitation of Liability"},
            {"category": "renewal_notice", "term_key": "renewal_opt_out", "label": "Renewal Opt-Out Notice", "value_text": "30 days prior to expiry", "numeric_value": 30, "unit": "days", "clause_ref": "3. Term & Renewal"},
        ],
        "default_deliverables_json": [
            {"title": "Quarterly Executive Business Review (QBR)", "deliverable_type": "report", "project_phase": "Governance", "offset_days": 90, "weight_pct": 50},
            {"title": "Annual SLA & Compliance Certificate", "deliverable_type": "compliance_cert", "project_phase": "Governance", "offset_days": 330, "weight_pct": 50},
        ],
    },
    {
        "name": "Vendor & Supply Agreement",
        "description": "Procurement contract tracking delivery lead times, SLA uptime, and compliance certificates.",
        "contract_type": "vendor_supply",
        "default_project_category": "procurement",
        "body_html": (
            "<h1>VENDOR &amp; SUPPLY AGREEMENT</h1>"
            "<p>Entered into for Project <strong>{{project_name}}</strong> between the Organization and Supplier <strong>{{counterparty_name}}</strong>.</p>"
            "<h2>1. Supply &amp; Delivery SLA</h2><p>Supplier guarantees delivery within 14 days of each Purchase Order.</p>"
            "<h2>2. Pricing &amp; Invoicing</h2><p>Contract ceiling: <strong>{{currency}} {{deal_value}}</strong>. Net 30 payment terms.</p>"
        ),
        "variables_json": [
            {"key": "counterparty_name", "label": "Vendor / Supplier Name", "type": "text", "required": True},
            {"key": "deal_value", "label": "Contract Ceiling", "type": "text", "required": False},
            {"key": "effective_date", "label": "Effective Date", "type": "date", "required": False},
        ],
        "default_key_terms_json": [
            {"category": "sla", "term_key": "delivery_lead_time", "label": "Delivery Lead Time", "value_text": "14 calendar days from PO", "numeric_value": 14, "unit": "days", "clause_ref": "1. Supply & Delivery SLA"},
            {"category": "financial", "term_key": "payment_terms", "label": "Payment Terms", "value_text": "Net 30 days", "clause_ref": "2. Pricing & Invoicing"},
        ],
        "default_deliverables_json": [
            {"title": "Initial Supply Batch Delivery & QA Inspection", "deliverable_type": "acceptance_gate", "project_phase": "Fulfillment", "offset_days": 21, "weight_pct": 60},
            {"title": "Insurance & Tax Compliance Certificate", "deliverable_type": "compliance_cert", "project_phase": "Compliance", "offset_days": 30, "weight_pct": 40},
        ],
    },
    {
        "name": "Mutual Non-Disclosure Agreement (NDA)",
        "description": "Bilateral confidentiality agreement with 5-year survival term.",
        "contract_type": "nda",
        "default_project_category": "legal_governance",
        "body_html": (
            "<h1>MUTUAL NON-DISCLOSURE AGREEMENT</h1>"
            "<p>This Mutual NDA is entered into for Project <strong>{{project_name}}</strong> between the Organization and <strong>{{counterparty_name}}</strong>, effective <strong>{{effective_date}}</strong>.</p>"
            "<h2>1. Confidential Information</h2><p>Both parties agree to protect all non-public technical, financial, and commercial information.</p>"
            "<h2>2. Survival Term</h2><p>Confidentiality obligations survive for five (5) years from the date of disclosure.</p>"
        ),
        "variables_json": [
            {"key": "counterparty_name", "label": "Counterparty Legal Name", "type": "text", "required": True},
            {"key": "effective_date", "label": "Effective Date", "type": "date", "required": False},
            {"key": "governing_law", "label": "Governing Law", "type": "text", "default": "Kenya"},
        ],
        "default_key_terms_json": [
            {"category": "liability_ip", "term_key": "confidentiality_survival", "label": "Confidentiality Survival", "value_text": "5 years from disclosure", "numeric_value": 5, "unit": "years", "clause_ref": "2. Survival Term"},
        ],
        "default_deliverables_json": [],
    },
]


def ensure_default_templates(organization_id: int, actor=None) -> list[ContractTemplate]:
    """Seed built-in published Contract Templates once per tenant."""
    ensure_contract_workflow_table()
    existing = ContractTemplate.query.filter_by(organization_id=organization_id).all()
    if existing:
        return existing
    now = datetime.utcnow()
    created = []
    for tpl in _SYSTEM_TEMPLATES:
        row = ContractTemplate(
            organization_id=organization_id,
            name=tpl["name"],
            description=tpl["description"],
            contract_type=tpl["contract_type"],
            default_project_category=tpl["default_project_category"],
            state="published",
            version=1,
            body_html=tpl["body_html"],
            variables_json=tpl["variables_json"],
            default_key_terms_json=tpl["default_key_terms_json"],
            default_deliverables_json=tpl["default_deliverables_json"],
            policy_json={"routing_mode": "parallel"},
            is_system=True,
            created_by_id=getattr(actor, "id", None),
            published_at=now,
        )
        db.session.add(row)
        created.append(row)
    db.session.commit()
    return created


def get_or_create_workflow(doc: TSDocument, actor) -> ContractWorkflow:
    ensure_contract_workflow_table()
    wf = ContractWorkflow.query.filter_by(
        document_id=doc.id, organization_id=doc.organization_id
    ).first()
    if wf is None:
        default_proj = ensure_default_project(doc.organization_id, actor)
        init_stage = normalize_stage(doc.status)
        init_cstatus = stage_to_canonical_status(init_stage)
        wf = ContractWorkflow(
            organization_id=doc.organization_id,
            document_id=doc.id,
            project_id=default_proj.id,
            contract_number=f"CTR-{datetime.utcnow().year}-{doc.id:04d}",
            contract_status=init_cstatus,
            stage=init_stage,
            edit_locked=init_stage in LOCKED_STAGES or init_cstatus != "DRAFT",
            checklist_json={
                "commercial_terms": False,
                "liability_indemnity": False,
                "confidentiality_data": False,
                "governing_law": False,
            },
            signers_json=[
                {
                    "id": "sig-org",
                    "order": 1,
                    "name": actor_label(actor),
                    "email": getattr(actor, "email", "") or "",
                    "role": "Authorized Signatory (Organization)",
                    "status": "signed" if init_stage == "signed" else "pending",
                    "signed_at": "",
                    "signature_text": "",
                    "signature_svg": "",
                }
            ],
            events_json=[
                {
                    "at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                    "actor": actor_label(actor),
                    "action": "Contract lifecycle initialized",
                    "detail": f"Status: {init_cstatus} · Project: {default_proj.project_code}",
                }
            ],
        )
        db.session.add(wf)
        db.session.commit()
    elif wf.project_id is None:
        default_proj = ensure_default_project(doc.organization_id, actor)
        wf.project_id = default_proj.id
        db.session.commit()
    return wf


def has_active_legal_hold(wf: ContractWorkflow) -> bool:
    if not wf.evidence_retention_id:
        return False
    hold = (
        EvidenceLegalHold.query.filter_by(
            retention_id=wf.evidence_retention_id,
            organization_id=wf.organization_id,
        )
        .filter(EvidenceLegalHold.released_at.is_(None))
        .first()
    )
    return hold is not None


def transition_stage(
    *,
    doc: TSDocument,
    wf: ContractWorkflow,
    actor,
    target_stage: str,
    note: str = "",
) -> tuple[bool, str | None]:
    if target_stage not in STAGE_LABELS:
        return False, "invalid_stage"

    if target_stage == "closed" and has_active_legal_hold(wf):
        return False, "Cannot archive contract while an active legal hold is placed on its evidence retention."

    prev = wf.stage
    wf.stage = target_stage
    wf.contract_status = stage_to_canonical_status(target_stage)
    wf.edit_locked = target_stage in LOCKED_STAGES or wf.contract_status != "DRAFT"

    if target_stage in ("signed", "suspended", "expired"):
        doc.status = "finalized"
        if target_stage == "signed":
            wf.closed_at = wf.closed_at or datetime.utcnow()
            wf.execution_sha256 = wf.execution_sha256 or doc.ciphertext_sha256
    elif target_stage == "closed":
        doc.status = "archived"
    else:
        doc.status = "draft"

    append_workflow_event(
        wf,
        actor,
        f"Stage changed to {STAGE_LABELS[target_stage]} ({wf.contract_status})",
        f"From {STAGE_LABELS.get(prev, prev)}" + (f" · {note}" if note else ""),
    )
    emit_contract_security_event(
        organization_id=doc.organization_id,
        actor_id=actor.id,
        action="contract.stage_change",
        document_id=doc.id,
        outcome="success",
    )
    if target_stage == "signature":
        emit_contract_outbox(
            organization_id=doc.organization_id,
            event_type="contract.sent_for_signature",
            document_id=doc.id,
            payload={"document_id": doc.id, "contract_number": wf.contract_number, "stage": target_stage},
        )
    return True, None


def suspend_contract(
    *,
    doc: TSDocument,
    wf: ContractWorkflow,
    actor,
    reason: str,
    expected_resume_date: str = "",
) -> tuple[bool, str | None]:
    """Transition SIGNED -> SUSPENDED and pause active deliverable timers."""
    if wf.canonical_status() != "SIGNED":
        return False, "Only SIGNED contracts can be suspended."
    if not reason.strip():
        return False, "Suspension reason is required."

    wf.contract_status = "SUSPENDED"
    wf.stage = "suspended"
    wf.suspended_at = datetime.utcnow()
    wf.suspension_reason = reason.strip()[:500]
    wf.expected_resume_date = (expected_resume_date or "").strip()[:32] or None
    wf.edit_locked = True
    doc.status = "finalized"

    # Pause non-terminal deliverables
    paused_cnt = 0
    for d in ContractDeliverable.query.filter_by(
        contract_id=wf.id, organization_id=doc.organization_id
    ).all():
        if d.status in ("not_started", "in_progress", "overdue"):
            d.status = "suspended"
            paused_cnt += 1

    append_workflow_event(
        wf,
        actor,
        "Contract SUSPENDED",
        f"{wf.suspension_reason}" + (f" · {paused_cnt} deliverables paused" if paused_cnt else ""),
    )
    emit_contract_security_event(
        organization_id=doc.organization_id,
        actor_id=actor.id,
        action="contract.suspended",
        document_id=doc.id,
    )
    emit_contract_outbox(
        organization_id=doc.organization_id,
        event_type="contract.suspended",
        document_id=doc.id,
        payload={"document_id": doc.id, "contract_number": wf.contract_number, "reason": wf.suspension_reason},
    )
    db.session.commit()
    return True, None


def resume_contract(
    *,
    doc: TSDocument,
    wf: ContractWorkflow,
    actor,
    note: str = "",
    shift_due_dates_days: int = 0,
) -> tuple[bool, str | None]:
    """Transition SUSPENDED -> SIGNED and resume paused deliverable timers."""
    if wf.canonical_status() != "SUSPENDED":
        return False, "Only SUSPENDED contracts can be resumed."

    wf.contract_status = "SIGNED"
    wf.stage = "signed"
    wf.suspended_at = None
    wf.suspension_reason = None
    wf.expected_resume_date = None
    wf.edit_locked = True
    doc.status = "finalized"

    shift_days = max(0, min(365, int(shift_due_dates_days or 0)))
    resumed_cnt = 0
    for d in ContractDeliverable.query.filter_by(
        contract_id=wf.id, organization_id=doc.organization_id, status="suspended"
    ).all():
        d.status = "in_progress"
        if shift_days and d.due_date:
            try:
                dt = datetime.strptime(d.due_date[:10], "%Y-%m-%d") + timedelta(days=shift_days)
                d.due_date = dt.strftime("%Y-%m-%d")
            except ValueError:
                pass
        resumed_cnt += 1

    append_workflow_event(
        wf,
        actor,
        "Contract RESUMED (Active / Signed)",
        (note.strip() or "Resumed from suspension")
        + (f" · {resumed_cnt} deliverables resumed" if resumed_cnt else "")
        + (f" (+{shift_days}d shift)" if shift_days else ""),
    )
    emit_contract_security_event(
        organization_id=doc.organization_id,
        actor_id=actor.id,
        action="contract.resumed",
        document_id=doc.id,
    )
    emit_contract_outbox(
        organization_id=doc.organization_id,
        event_type="contract.resumed",
        document_id=doc.id,
        payload={"document_id": doc.id, "contract_number": wf.contract_number, "note": note},
    )
    db.session.commit()
    return True, None


def terminate_contract_record(
    *,
    doc: TSDocument,
    wf: ContractWorkflow,
    actor,
    reason: str,
    termination_type: str = "mutual",
) -> tuple[bool, str | None]:
    """Transition DRAFT/SIGNED/SUSPENDED -> TERMINATED."""
    if not reason.strip():
        return False, "Termination reason is required."
    valid_types = ("mutual", "for_cause", "for_convenience", "expiry", "probation_failed", "cancelled_draft")
    t_type = termination_type if termination_type in valid_types else "mutual"

    wf.contract_status = "TERMINATED"
    wf.stage = "expired"
    wf.terminated_at = datetime.utcnow()
    wf.termination_type = t_type
    wf.termination_reason = reason.strip()[:500]
    wf.edit_locked = True
    doc.status = "finalized"

    # Cancel remaining non-accepted deliverables
    for d in ContractDeliverable.query.filter_by(
        contract_id=wf.id, organization_id=doc.organization_id
    ).all():
        if d.status not in ("accepted", "cancelled"):
            d.status = "cancelled"

    append_workflow_event(
        wf, actor, f"Contract TERMINATED ({t_type.replace('_', ' ')})", wf.termination_reason
    )
    emit_contract_security_event(
        organization_id=doc.organization_id,
        actor_id=actor.id,
        action="contract.terminated",
        document_id=doc.id,
    )
    emit_contract_outbox(
        organization_id=doc.organization_id,
        event_type="contract.terminated",
        document_id=doc.id,
        payload={
            "document_id": doc.id,
            "contract_number": wf.contract_number,
            "termination_type": t_type,
            "reason": wf.termination_reason,
        },
    )
    db.session.commit()
    return True, None


def compute_deliverable_progress(deliverables: list[ContractDeliverable]) -> dict[str, Any]:
    if not deliverables:
        return {"total": 0, "accepted": 0, "in_progress": 0, "suspended": 0, "pct": 0}
    total_weight = sum(max(1, d.weight_pct or 10) for d in deliverables if d.status != "cancelled")
    done_weight = sum(max(1, d.weight_pct or 10) for d in deliverables if d.status == "accepted")
    pct = int(round((done_weight / total_weight) * 100)) if total_weight > 0 else 0
    return {
        "total": len(deliverables),
        "accepted": sum(1 for d in deliverables if d.status == "accepted"),
        "in_progress": sum(1 for d in deliverables if d.status in ("in_progress", "submitted")),
        "suspended": sum(1 for d in deliverables if d.status == "suspended"),
        "pct": pct,
    }


def instantiate_contract_from_template(
    *,
    template: ContractTemplate,
    project: Project,
    actor,
    title: str,
    variables: dict[str, Any],
) -> tuple[TSDocument, ContractWorkflow]:
    """Create a Project-associated Contract from a published ContractTemplate + auto-seed Key Terms & Deliverables."""
    now = datetime.utcnow()
    eff_date = str(variables.get("effective_date") or now.strftime("%Y-%m-%d")).strip()[:32]
    try:
        base_dt = datetime.strptime(eff_date[:10], "%Y-%m-%d")
    except ValueError:
        base_dt = now
        eff_date = now.strftime("%Y-%m-%d")

    probation_days = int(variables.get("probation_days") or 90)
    probation_end = (base_dt + timedelta(days=probation_days)).strftime("%Y-%m-%d")

    from app.models.organization import Organization
    from app.services.placeholder_engine import build_placeholder_context, substitute_known_placeholders

    org = db.session.get(Organization, project.organization_id)
    ctx = build_placeholder_context(
        project=project,
        organization=org,
        actor=actor,
        extra={
            "project_name": project.name,
            "project_code": project.project_code,
            "counterparty_name": str(variables.get("counterparty_name") or "Counterparty"),
            "deal_value": str(variables.get("deal_value") or "0.00"),
            "currency": str(variables.get("currency") or project.currency or "USD"),
            "effective_date": eff_date,
            "expiration_date": str(variables.get("expiration_date") or ""),
            "probation_end_date": probation_end,
            "governing_law": str(variables.get("governing_law") or "Kenya"),
            "document_ref": f"CTR-{datetime.utcnow().year}-{project.project_code}",
            **(variables or {}),
        },
    )

    rendered_html = substitute_known_placeholders(template.body_html or "<p></p>", ctx)

    doc_title = (title or f"{template.name} — {ctx['counterparty_name']}")[:255]
    env = pack_content(
        html=sanitize_html(rendered_html),
        description=f"Created from template {template.name} under project {project.project_code}",
        extras={"template_id": template.id, "project_id": project.id},
    )
    ct = encrypt_content_envelope(env, organization_id=project.organization_id)
    doc = TSDocument(
        organization_id=project.organization_id,
        created_by_id=actor.id,
        title=doc_title,
        description=f"Project {project.project_code} · {template.name}",
        export_policy="pdf_allowed",
        status="draft",
        ciphertext=ct,
        ciphertext_sha256=sha256_hex(ct),
        plaintext_bytes=len(env),
        version=1,
    )
    db.session.add(doc)
    db.session.flush()

    wf = ContractWorkflow(
        organization_id=project.organization_id,
        document_id=doc.id,
        project_id=project.id,
        template_id=template.id,
        contract_number=f"CTR-{now.year}-{doc.id:04d}",
        contract_type=template.contract_type,
        contract_status="DRAFT",
        stage="draft",
        counterparty_name=(ctx.get("counterparty_name") or "Counterparty")[:200],
        deal_value=str(variables.get("deal_value") or "")[:64] or None,
        currency=(ctx.get("currency") or "USD")[:12],
        effective_date=eff_date,
        expiration_date=(ctx.get("expiration_date") or "")[:32] or None,
        governing_law=(ctx.get("governing_law") or "Kenya")[:120],
        letterhead_id=template.default_letterhead_id,
        stamp_id=template.default_stamp_id,
        routing_mode=(template.policy_json or {}).get("routing_mode", "parallel"),
        checklist_json={
            "commercial_terms": False,
            "liability_indemnity": False,
            "confidentiality_data": False,
            "governing_law": False,
        },
        signers_json=[
            {
                "id": "sig-org",
                "order": 1,
                "name": actor_label(actor),
                "email": getattr(actor, "email", "") or "",
                "role": "Authorized Signatory (Organization)",
                "status": "pending",
                "signed_at": "",
                "signature_text": "",
                "signature_svg": "",
            }
        ],
        events_json=[
            {
                "at": now.strftime("%Y-%m-%d %H:%M UTC"),
                "actor": actor_label(actor),
                "action": "Created from Contract Template",
                "detail": f"Template: {template.name} · Project: {project.project_code}",
            }
        ],
    )
    db.session.add(wf)
    db.session.flush()

    # Auto-seed Key Terms blueprint
    for kt in (template.default_key_terms_json or []):
        offset = kt.get("offset_days")
        if kt.get("category") == "probation" and variables.get("probation_days"):
            offset = probation_days
        end_str = (base_dt + timedelta(days=int(offset))).strftime("%Y-%m-%d") if offset else None
        db.session.add(
            ContractKeyTerm(
                organization_id=project.organization_id,
                contract_id=wf.id,
                category=str(kt.get("category") or "custom")[:32],
                term_key=str(kt.get("term_key") or "")[:64] or None,
                label=str(kt.get("label") or "Key Term")[:200],
                value_text=str(kt.get("value_text") or "")[:300],
                numeric_value=kt.get("numeric_value"),
                unit=str(kt.get("unit") or "")[:32] or None,
                start_date=eff_date if offset else None,
                end_date=end_str,
                alert_days_before=int(kt.get("alert_days_before") or 14),
                status="active",
                clause_ref=str(kt.get("clause_ref") or "")[:120] or None,
            )
        )

    # Auto-seed Deliverables blueprint
    for dl in (template.default_deliverables_json or []):
        offset = int(dl.get("offset_days") or 30)
        due_str = (base_dt + timedelta(days=offset)).strftime("%Y-%m-%d")
        db.session.add(
            ContractDeliverable(
                organization_id=project.organization_id,
                contract_id=wf.id,
                title=str(dl.get("title") or "Milestone")[:200],
                description=str(dl.get("description") or "")[:500] or None,
                deliverable_type=str(dl.get("deliverable_type") or "milestone")[:32],
                project_phase=str(dl.get("project_phase") or "")[:80] or None,
                owner_name=actor_label(actor),
                counterparty_owner=ctx["counterparty_name"][:140],
                due_date=due_str,
                weight_pct=int(dl.get("weight_pct") or 10),
                payment_amount=dl.get("payment_amount"),
                status="not_started",
            )
        )

    emit_contract_security_event(
        organization_id=project.organization_id,
        actor_id=actor.id,
        action="contract.created_from_template",
        document_id=doc.id,
    )
    db.session.commit()
    return doc, wf


def render_contract_pdf(doc: TSDocument, wf: ContractWorkflow) -> bytes:
    """Render the decrypted TSD HTML + Full-Fidelity Vector Letterhead & Margins + Execution Certificate.

    When an official ``TSDLetterhead`` is attached, renders the complete vector letterhead
    stationery (paper stock, background pattern, watermark, logo, header, ref bar, footer)
    via ReportLab (``render_letterhead_pdf_from_config``) and composites the letterhead-styled
    contract body & execution certificate inside the approved margin clearance box via ``pypdf``
    so the exported PDF matches the studio layout with zero missing content.
    """
    env = decrypt_content_envelope(doc.ciphertext, organization_id=doc.organization_id)
    extras = env.get("extras") if isinstance(env.get("extras"), dict) else {}
    if extras.get("external_original_pdf_b64"):
        try:
            import base64
            raw_pdf = base64.b64decode(extras["external_original_pdf_b64"])
            if raw_pdf.startswith(b"%PDF-"):
                return raw_pdf
        except Exception:
            pass
    body_html = env.get("html") or "<p>(Empty contract)</p>"
    try:
        from app.models.organization import Organization
        from app.services.placeholder_engine import build_placeholder_context, resolve_placeholders_for_export

        proj = db.session.get(Project, wf.project_id) if wf.project_id else None
        org = db.session.get(Organization, doc.organization_id) if doc.organization_id else None
        pdf_ctx = build_placeholder_context(doc=doc, wf=wf, project=proj, organization=org)
        body_html = resolve_placeholders_for_export(body_html, pdf_ctx)
    except Exception:
        pass

    lh = None
    page_size = None
    orientation = None
    margin_mm = None
    margin_top_mm = None
    margin_bottom_mm = None
    lh_extra_css = ""

    if wf.letterhead_id:
        try:
            from app.models.tsd_letterhead import LETTERHEAD_FONT_STACKS, TSDLetterhead

            lh = (
                TSDLetterhead.query.filter_by(
                    id=wf.letterhead_id, organization_id=doc.organization_id
                )
                .filter(TSDLetterhead.deleted_at.is_(None))
                .first()
            )
            if lh is not None:
                lay = lh.layout or {}
                page_size = str(lay.get("paper_size") or "a4").lower()
                orientation = str(lay.get("orientation") or "portrait").lower()
                margin_mm = max(10, min(40, int(lay.get("margin_mm") or 22)))
                base_my = max(10, min(40, int(lay.get("margin_y_mm") or margin_mm)))
                # Clear the vector letterhead header + optional ref bar cleanly on every page
                logo_h = int(lay.get("logo_height_px") or 50)
                hdr_min = int(lay.get("header_min_height") or 0)
                extra_hdr_mm = max(0, int((max(logo_h, hdr_min) - 54) * 0.28))
                margin_top_mm = base_my + (50 if lay.get("show_ref_bar", True) else 38) + extra_hdr_mm
                margin_bottom_mm = base_my + (22 if (lay.get("directors") or lay.get("bank_details")) else 16)

                font_key = str(lay.get("font_style") or "sans").lower()
                # Map to ReportLab/xhtml2pdf built-in crisp families
                pdf_font = (
                    "Times-Roman, Georgia, serif"
                    if font_key in ("serif", "legal", "garamond")
                    else ("Courier, monospace" if font_key == "mono" else "Helvetica, Arial, sans-serif")
                )
                accent = html_std.escape(str(lay.get("accent_color") or "#002769"))
                brand2 = html_std.escape(str(lay.get("brand_secondary") or "#02982e"))
                sec = html_std.escape(str(lay.get("secondary_color") or "#1d3648"))
                lh_extra_css = (
                    f"body {{ font-family: {pdf_font}; color: {sec}; }}\n"
                    f"h1 {{ color: {accent}; margin-top: 4pt; }}\n"
                    f"h2 {{ color: {accent}; border-bottom: 0.75pt solid {accent}; padding-bottom: 3pt; }}\n"
                    f"h3 {{ color: {sec}; }}\n"
                    f"blockquote {{ border-left: 2.5pt solid {brand2}; }}\n"
                )
        except Exception:
            lh = None

    signers = wf.signers_json or []
    cert_html = ""
    if wf.canonical_status() in ("SIGNED", "SUSPENDED", "TERMINATED") or any(
        s.get("status") == "signed" for s in signers
    ):
        rows_html = []
        for s in signers:
            st = "Executed" if s.get("status") == "signed" else "Pending"
            sig_disp = html_std.escape(s.get("signature_text") or s.get("name") or "")
            rows_html.append(
                "<tr>"
                f"<td style='padding:6px 8px;border:1px solid #d5dce6;'><strong>{html_std.escape(s.get('name') or '')}</strong><br/><span style='color:#4c6273;font-size:8.5pt;'>{html_std.escape(s.get('role') or '')}</span></td>"
                f"<td style='padding:6px 8px;border:1px solid #d5dce6;font-style:italic;color:#002769;'>{sig_disp if st == 'Executed' else '—'}</td>"
                f"<td style='padding:6px 8px;border:1px solid #d5dce6;'>{html_std.escape(st)}</td>"
                f"<td style='padding:6px 8px;border:1px solid #d5dce6;'>{html_std.escape(s.get('signed_at') or '—')}</td>"
                "</tr>"
            )
        cert_html = (
            "<div style='page-break-before:always;border:1px solid #d5dce6;padding:14pt;'>"
            "<h2 style='margin:0 0 6pt;color:#002769;'>TRUSTSEAL Certificate of Contract Execution</h2>"
            f"<p style='font-size:9pt;color:#4c6273;margin:0 0 10pt;'>Contract #{html_std.escape(wf.contract_number or str(doc.id))} · "
            f"Status: <strong>{html_std.escape(wf.canonical_status())}</strong> · "
            f"Counterparty: {html_std.escape(wf.counterparty_name or '—')} · "
            f"Closed: {html_std.escape(wf.closed_at.strftime('%Y-%m-%d %H:%M UTC') if wf.closed_at else 'In Progress')}</p>"
            "<table style='width:100%;border-collapse:collapse;font-size:9pt;'>"
            "<thead><tr style='background:#f6f8fb;'>"
            "<th style='padding:6px 8px;border:1px solid #d5dce6;text-align:left;'>Signatory</th>"
            "<th style='padding:6px 8px;border:1px solid #d5dce6;text-align:left;'>Signature</th>"
            "<th style='padding:6px 8px;border:1px solid #d5dce6;text-align:left;'>Status</th>"
            "<th style='padding:6px 8px;border:1px solid #d5dce6;text-align:left;'>Executed At (UTC)</th>"
            "</tr></thead><tbody>" + "".join(rows_html) + "</tbody></table>"
            f"<p style='margin-top:10pt;font-size:8pt;color:#4c6273;font-family:Courier,monospace;'>Vault SHA-256: {html_std.escape(doc.ciphertext_sha256)}</p>"
            "</div>"
        )

    body_pdf = render_html_to_pdf(
        html=body_html + cert_html,
        title=doc.title,
        document_id=doc.id,
        version=doc.version,
        tenant_id=doc.organization_id,
        page_size=page_size,
        orientation=orientation,
        margin_mm=margin_mm,
        margin_top_mm=margin_top_mm,
        margin_bottom_mm=margin_bottom_mm,
        extra_css=lh_extra_css,
        include_default_footer=(lh is None),
    )

    if lh is not None:
        try:
            import copy
            import io as _io
            from pypdf import PdfReader, PdfWriter
            from app.services.letterhead_pdf import render_letterhead_pdf_from_config

            lh_pdf_bytes = render_letterhead_pdf_from_config(
                lh.layout or {}, title=lh.name or doc.title
            )
            body_reader = PdfReader(_io.BytesIO(body_pdf))
            writer = PdfWriter()
            for idx, b_page in enumerate(body_reader.pages):
                # Re-parse a clean copy of the vector letterhead template per page
                lh_reader = PdfReader(_io.BytesIO(lh_pdf_bytes))
                lh_page = lh_reader.pages[0]
                lh_page.merge_page(b_page)
                writer.add_page(lh_page)
            out_buf = _io.BytesIO()
            writer.write(out_buf)
            return out_buf.getvalue()
        except Exception:
            pass

    return body_pdf


def close_and_seal_contract(
    *,
    doc: TSDocument,
    wf: ContractWorkflow,
    actor,
    stamp_id: int | None = None,
    closing_note: str = "",
) -> dict[str, Any]:
    """Atomic deal-closing ceremony: freeze, stamp receipt, render PDF, retain evidence, audit."""
    if stamp_id:
        wf.stamp_id = int(stamp_id)

    now = datetime.utcnow()
    now_str = now.strftime("%Y-%m-%d %H:%M UTC")
    signers = list(wf.signers_json or [])
    for s in signers:
        if s.get("status") != "signed":
            s["status"] = "signed"
            s["signed_at"] = now_str
            s["signature_text"] = s.get("signature_text") or s.get("name") or actor_label(actor)
    wf.signers_json = signers
    flag_modified(wf, "signers_json")

    wf.contract_status = "SIGNED"
    wf.stage = "signed"
    wf.closed_at = now
    wf.edit_locked = True
    doc.status = "finalized"

    # Activate any not_started deliverables
    for d in ContractDeliverable.query.filter_by(
        contract_id=wf.id, organization_id=doc.organization_id, status="not_started"
    ).all():
        d.status = "in_progress"

    receipt_id = wf.stamp_receipt_id
    if wf.stamp_id and not receipt_id:
        try:
            from app.models.tsd_stamp import TSDStamp
            from app.services.tsd_stamp_receipts import issue_receipt

            stamp = TSDStamp.query.filter_by(
                id=wf.stamp_id, organization_id=doc.organization_id
            ).first()
            if stamp is not None:
                receipt = issue_receipt(
                    organization_id=doc.organization_id,
                    stamp=stamp,
                    placed_by_id=actor.id,
                    document_id=doc.id,
                    context_label=f"Contract Execution · {doc.title[:120]}",
                    context_svg=stamp.svg or f"<svg data-stamp='{stamp.id}'/>",
                )
                receipt_id = receipt.id
                wf.stamp_receipt_id = receipt_id
        except Exception:
            pass

    pdf_sha = doc.ciphertext_sha256
    try:
        pdf_bytes = render_contract_pdf(doc, wf)
        pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()
    except Exception:
        pass
    wf.execution_sha256 = pdf_sha

    if not wf.evidence_retention_id:
        art_type = "stamped_pdf" if receipt_id else "finalized_pdf"
        existing_ret = EvidenceRetention.query.filter_by(
            organization_id=doc.organization_id,
            artifact_type=art_type,
            artifact_id=doc.id,
        ).first()
        if existing_ret is not None:
            wf.evidence_retention_id = existing_ret.id
        else:
            retention = EvidenceRetention(
                organization_id=doc.organization_id,
                artifact_type=art_type,
                artifact_id=doc.id,
                artifact_sha256=pdf_sha,
                retain_until=now + timedelta(days=365 * 7),
                created_by_id=actor.id,
            )
            db.session.add(retention)
            db.session.flush()
            wf.evidence_retention_id = retention.id

    append_workflow_event(
        wf,
        actor,
        "Contract SIGNED, Sealed & Preserved with TrustSeal",
        f"SHA-256 {pdf_sha[:16]}…"
        + (f" · Retention #{wf.evidence_retention_id}" if wf.evidence_retention_id else "")
        + (f" · Stamp Receipt #{receipt_id}" if receipt_id else "")
        + (f" · {closing_note}" if closing_note else ""),
    )
    emit_contract_security_event(
        organization_id=doc.organization_id,
        actor_id=actor.id,
        action="contract.closed",
        document_id=doc.id,
        outcome=f"receipt:{receipt_id}" if receipt_id else "success",
    )
    emit_contract_outbox(
        organization_id=doc.organization_id,
        event_type="contract.executed",
        document_id=doc.id,
        payload={
            "document_id": doc.id,
            "contract_number": wf.contract_number,
            "contract_status": "SIGNED",
            "execution_sha256": pdf_sha,
            "evidence_retention_id": wf.evidence_retention_id,
            "stamp_receipt_id": receipt_id,
        },
    )
    db.session.commit()
    return {
        "workflow": wf.to_dict(),
        "status": doc.status,
        "contract_status": wf.contract_status,
        "execution_sha256": pdf_sha,
        "evidence_retention_id": wf.evidence_retention_id,
        "stamp_receipt_id": receipt_id,
    }


def _html_to_lines(raw_html: str) -> list[str]:
    text_only = re.sub(r"</(p|div|h[1-6]|li|tr|blockquote)>", "\n", raw_html or "", flags=re.I)
    text_only = re.sub(r"<br\s*/?>", "\n", text_only, flags=re.I)
    text_only = re.sub(r"<[^>]+>", "", text_only)
    text_only = html_std.unescape(text_only)
    return [line.strip() for line in text_only.splitlines() if line.strip()]


def compute_version_diff(doc: TSDocument, from_version: int, to_version: int | None = None) -> dict[str, Any]:
    v_from = TSDocumentVersion.query.filter_by(tsd_id=doc.id, version=from_version).first()
    from_html = (
        (decrypt_content_envelope(v_from.ciphertext, organization_id=doc.organization_id) or {}).get("html", "")
        if v_from is not None
        else ""
    )

    if to_version is None or to_version == doc.version:
        to_version = doc.version
        to_html = (decrypt_content_envelope(doc.ciphertext, organization_id=doc.organization_id) or {}).get("html", "")
    else:
        v_to = TSDocumentVersion.query.filter_by(tsd_id=doc.id, version=to_version).first()
        to_html = (
            (decrypt_content_envelope(v_to.ciphertext, organization_id=doc.organization_id) or {}).get("html", "")
            if v_to is not None
            else ""
        )

    a_lines = _html_to_lines(from_html)
    b_lines = _html_to_lines(to_html)
    diff_rows = []
    added = removed = unchanged = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a_lines, b_lines).get_opcodes():
        if tag == "equal":
            for line in a_lines[i1:i2]:
                diff_rows.append({"type": "equal", "text": line})
                unchanged += 1
        elif tag in ("delete", "replace"):
            for line in a_lines[i1:i2]:
                diff_rows.append({"type": "del", "text": line})
                removed += 1
            if tag == "replace":
                for line in b_lines[j1:j2]:
                    diff_rows.append({"type": "add", "text": line})
                    added += 1
        elif tag == "insert":
            for line in b_lines[j1:j2]:
                diff_rows.append({"type": "add", "text": line})
                added += 1

    return {
        "from_version": from_version,
        "to_version": to_version,
        "added": added,
        "removed": removed,
        "unchanged": unchanged,
        "lines": diff_rows,
    }


def save_contract_html(doc: TSDocument, wf: ContractWorkflow, actor, raw_html: str) -> tuple[bool, str | None]:
    if wf.edit_locked or wf.stage in LOCKED_STAGES or wf.canonical_status() != "DRAFT":
        return False, "Contract is edit-locked in its current status/stage. Return to Draft or Legal Review to edit."

    clean_html = sanitize_html(raw_html or "")
    prev_env = decrypt_content_envelope(doc.ciphertext, organization_id=doc.organization_id) or {}
    snap = TSDocumentVersion(
        tsd_id=doc.id,
        version=doc.version,
        ciphertext=doc.ciphertext,
        ciphertext_sha256=doc.ciphertext_sha256,
        plaintext_bytes=doc.plaintext_bytes,
        created_by_id=actor.id,
        change_note="Saved from Contract Workspace",
    )
    db.session.add(snap)

    new_env = pack_content(
        html=clean_html,
        description=doc.description,
        extras=prev_env.get("extras") if isinstance(prev_env.get("extras"), dict) else None,
    )
    ct = encrypt_content_envelope(new_env, organization_id=doc.organization_id)
    pt_bytes = len(new_env)
    doc.ciphertext = ct
    doc.ciphertext_sha256 = sha256_hex(ct)
    doc.plaintext_bytes = pt_bytes
    doc.version = (doc.version or 1) + 1
    doc.updated_at = datetime.utcnow()

    append_workflow_event(wf, actor, f"Saved document revision v{doc.version}", f"{pt_bytes} bytes")
    emit_contract_security_event(
        organization_id=doc.organization_id,
        actor_id=actor.id,
        action="contract.content_saved",
        document_id=doc.id,
    )
    db.session.commit()
    return True, None


def create_linked_contract(
    *,
    parent_doc: TSDocument,
    parent_wf: ContractWorkflow,
    actor,
    relationship_type: str = "amendment",
    title: str = "",
) -> tuple[TSDocument, ContractWorkflow]:
    allowed_rels = {
        "amendment": "Amendment",
        "addendum": "Addendum",
        "nce": "No-Cost Extension (NCE)",
        "costed_extension": "Costed Extension",
        "scope_variation": "Scope Variation",
        "renewal": "Renewal",
        "sow": "SOW",
    }
    rel = relationship_type if relationship_type in allowed_rels else "amendment"
    rel_label = allowed_rels[rel]
    new_title = (title or f"{rel_label} — {parent_doc.title}")[:255]

    parent_env = decrypt_content_envelope(parent_doc.ciphertext, organization_id=parent_doc.organization_id) or {}
    if rel == "renewal":
        body_html = parent_env.get("html") or ""
    else:
        body_html = (
            f"<h1>{html_std.escape(new_title)}</h1>"
            f"<p>This {html_std.escape(rel_label)} modifies and forms part of the principal agreement "
            f"<strong>{html_std.escape(parent_doc.title)}</strong> "
            f"(Ref: {html_std.escape(parent_wf.contract_number or str(parent_doc.id))}) "
            f"between the Organization and <strong>{html_std.escape(parent_wf.counterparty_name or 'Counterparty')}</strong>.</p>"
            "<h2>1. Amended Terms</h2><p>Specify amended clauses, pricing adjustments, or scope changes here.</p>"
            "<h2>2. Full Force and Effect</h2><p>Except as expressly modified herein, all terms of the Principal Agreement remain in full force and effect.</p>"
        )

    env = pack_content(
        html=sanitize_html(body_html),
        description=f"{rel_label} linked to {parent_wf.contract_number or parent_doc.title}",
        extras={"parent_contract_id": parent_wf.id, "project_id": parent_wf.project_id},
    )
    ct = encrypt_content_envelope(env, organization_id=parent_doc.organization_id)
    pt_bytes = len(env)
    new_doc = TSDocument(
        organization_id=parent_doc.organization_id,
        created_by_id=actor.id,
        title=new_title,
        description=f"{rel_label} linked to {parent_wf.contract_number or parent_doc.title}",
        export_policy=parent_doc.export_policy,
        status="draft",
        ciphertext=ct,
        ciphertext_sha256=sha256_hex(ct),
        plaintext_bytes=pt_bytes,
        version=1,
    )
    db.session.add(new_doc)
    db.session.flush()

    proj_id = parent_wf.project_id or ensure_default_project(parent_doc.organization_id, actor).id
    new_wf = ContractWorkflow(
        organization_id=parent_doc.organization_id,
        document_id=new_doc.id,
        project_id=proj_id,
        contract_number=f"CTR-{datetime.utcnow().year}-{new_doc.id:04d}",
        contract_type=rel,
        contract_status="DRAFT",
        stage="draft",
        counterparty_name=parent_wf.counterparty_name,
        deal_value=parent_wf.deal_value,
        currency=parent_wf.currency,
        governing_law=parent_wf.governing_law,
        letterhead_id=parent_wf.letterhead_id,
        stamp_id=parent_wf.stamp_id,
        parent_contract_id=parent_wf.id,
        relationship_type=rel,
        checklist_json={
            "commercial_terms": False,
            "liability_indemnity": False,
            "confidentiality_data": False,
            "governing_law": False,
        },
        signers_json=[
            {
                "id": "sig-org",
                "order": 1,
                "name": actor_label(actor),
                "email": getattr(actor, "email", "") or "",
                "role": "Authorized Signatory (Organization)",
                "status": "pending",
                "signed_at": "",
                "signature_text": "",
                "signature_svg": "",
            }
        ],
        events_json=[
            {
                "at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                "actor": actor_label(actor),
                "action": f"{rel_label} created",
                "detail": f"Linked to parent contract #{parent_wf.contract_number or parent_doc.id}",
            }
        ],
    )
    db.session.add(new_wf)
    append_workflow_event(parent_wf, actor, f"{rel_label} spawned", new_title)
    emit_contract_security_event(
        organization_id=parent_doc.organization_id,
        actor_id=actor.id,
        action=f"contract.{rel}_created",
        document_id=new_doc.id,
    )
    db.session.commit()
    return new_doc, new_wf


def apply_letterhead_to_contract(
    *,
    doc: TSDocument,
    wf: ContractWorkflow,
    actor,
    letterhead_id: int | None = None,
    preset_slug: str | None = None,
    custom_name: str = "",
) -> tuple[bool, str | None, dict[str, Any] | None]:
    """Attach, create-from-preset, or remove an official Letterhead on a contract."""
    from app.models.tsd_letterhead import (
        LETTERHEAD_PRESETS,
        TSDLetterhead,
        render_letterhead_parts,
    )

    lh = None
    if preset_slug:
        preset = next((p for p in LETTERHEAD_PRESETS if p["slug"] == preset_slug), None)
        if preset is None:
            return False, "Selected letterhead preset was not found.", None
        layout = dict(preset["layout"])
        hdr_html, ftr_html = render_letterhead_parts(layout)
        name = (custom_name or preset["label"]).strip()[:140]
        lh = TSDLetterhead(
            organization_id=doc.organization_id,
            created_by_id=actor.id,
            name=name,
            description=preset.get("description") or preset.get("doc_type") or "",
            is_default=False,
            status="active",
            layout=layout,
            header_html=hdr_html,
            footer_html=ftr_html,
        )
        db.session.add(lh)
        db.session.flush()
        wf.letterhead_id = lh.id
        append_workflow_event(wf, actor, "Applied new letterhead", f"{lh.name} (from preset)")
    elif letterhead_id:
        lh = (
            TSDLetterhead.query.filter_by(
                id=int(letterhead_id), organization_id=doc.organization_id
            )
            .filter(TSDLetterhead.deleted_at.is_(None))
            .first()
        )
        if lh is None:
            return False, "Selected letterhead was not found.", None
        wf.letterhead_id = lh.id
        append_workflow_event(wf, actor, "Applied official letterhead", lh.name)
    else:
        wf.letterhead_id = None
        append_workflow_event(wf, actor, "Removed letterhead", "Cleared stationery header/footer")

    emit_contract_security_event(
        organization_id=doc.organization_id,
        actor_id=actor.id,
        action="contract.letterhead_updated",
        document_id=doc.id,
    )
    db.session.commit()
    return True, None, (lh.to_dict() if lh else None)


def apply_template_to_contract(
    *,
    doc: TSDocument,
    wf: ContractWorkflow,
    template: ContractTemplate,
    actor,
    mode: str = "replace",
    variables: dict[str, Any] | None = None,
    seed_key_terms: bool = True,
    seed_deliverables: bool = True,
) -> tuple[bool, str | None, dict[str, Any]]:
    """Apply a published ContractTemplate directly onto an existing DRAFT contract."""
    if wf.edit_locked or wf.stage in LOCKED_STAGES or wf.canonical_status() != "DRAFT":
        return (
            False,
            "Contract is edit-locked in its current status/stage. Return to Draft to apply a template.",
            {},
        )

    now = datetime.utcnow()
    project = db.session.get(Project, wf.project_id) if wf.project_id else None
    vars_in = variables if isinstance(variables, dict) else {}

    eff_date = str(vars_in.get("effective_date") or wf.effective_date or now.strftime("%Y-%m-%d"))[:32]
    try:
        base_dt = datetime.strptime(eff_date[:10], "%Y-%m-%d")
    except ValueError:
        base_dt = now
        eff_date = now.strftime("%Y-%m-%d")

    probation_days = int(vars_in.get("probation_days") or 90)
    probation_end = (base_dt + timedelta(days=probation_days)).strftime("%Y-%m-%d")

    from app.models.organization import Organization
    from app.services.placeholder_engine import build_placeholder_context, substitute_known_placeholders

    org = db.session.get(Organization, doc.organization_id)
    ctx = build_placeholder_context(
        doc=doc,
        wf=wf,
        project=project,
        organization=org,
        actor=actor,
        extra={
            "project_name": project.name if project else "General Operations",
            "project_code": project.project_code if project else "PRJ-001",
            "counterparty_name": str(vars_in.get("counterparty_name") or wf.counterparty_name or "Counterparty"),
            "deal_value": str(vars_in.get("deal_value") or wf.deal_value or "0.00"),
            "currency": str(vars_in.get("currency") or wf.currency or (project.currency if project else "USD")),
            "effective_date": eff_date,
            "expiration_date": str(vars_in.get("expiration_date") or wf.expiration_date or ""),
            "probation_end_date": probation_end,
            "governing_law": str(vars_in.get("governing_law") or wf.governing_law or "Kenya"),
            **(vars_in or {}),
        },
    )

    rendered = substitute_known_placeholders(template.body_html or "<p></p>", ctx)

    if mode == "append":
        prev_env = decrypt_content_envelope(doc.ciphertext, organization_id=doc.organization_id) or {}
        final_html = (prev_env.get("html") or "") + "\n" + rendered
    else:
        final_html = rendered

    ok, err = save_contract_html(doc, wf, actor, final_html)
    if not ok:
        return False, err, {}

    wf.template_id = template.id
    wf.contract_type = template.contract_type
    if vars_in.get("counterparty_name"):
        wf.counterparty_name = str(vars_in["counterparty_name"]).strip()[:200]
    if vars_in.get("deal_value"):
        wf.deal_value = str(vars_in["deal_value"]).strip()[:64]
    if vars_in.get("effective_date"):
        wf.effective_date = eff_date
    if vars_in.get("governing_law"):
        wf.governing_law = str(vars_in["governing_law"]).strip()[:120]
    if template.default_letterhead_id and not wf.letterhead_id:
        wf.letterhead_id = template.default_letterhead_id

    added_terms = 0
    if seed_key_terms:
        existing_labels = {
            kt.label.lower()
            for kt in ContractKeyTerm.query.filter_by(
                contract_id=wf.id, organization_id=doc.organization_id
            ).all()
        }
        for kt in (template.default_key_terms_json or []):
            lbl = str(kt.get("label") or "Key Term")[:200]
            if lbl.lower() in existing_labels:
                continue
            offset = kt.get("offset_days")
            if kt.get("category") == "probation" and vars_in.get("probation_days"):
                offset = probation_days
            end_str = (base_dt + timedelta(days=int(offset))).strftime("%Y-%m-%d") if offset else None
            db.session.add(
                ContractKeyTerm(
                    organization_id=doc.organization_id,
                    contract_id=wf.id,
                    category=str(kt.get("category") or "custom")[:32],
                    term_key=str(kt.get("term_key") or "")[:64] or None,
                    label=lbl,
                    value_text=str(kt.get("value_text") or "")[:300],
                    numeric_value=kt.get("numeric_value"),
                    unit=str(kt.get("unit") or "")[:32] or None,
                    start_date=eff_date if offset else None,
                    end_date=end_str,
                    alert_days_before=int(kt.get("alert_days_before") or 14),
                    status="active",
                    clause_ref=str(kt.get("clause_ref") or "")[:120] or None,
                )
            )
            added_terms += 1

    added_deliverables = 0
    if seed_deliverables:
        existing_titles = {
            d.title.lower()
            for d in ContractDeliverable.query.filter_by(
                contract_id=wf.id, organization_id=doc.organization_id
            ).all()
        }
        for dl in (template.default_deliverables_json or []):
            ttl = str(dl.get("title") or "Milestone")[:200]
            if ttl.lower() in existing_titles:
                continue
            offset = int(dl.get("offset_days") or 30)
            due_str = (base_dt + timedelta(days=offset)).strftime("%Y-%m-%d")
            db.session.add(
                ContractDeliverable(
                    organization_id=doc.organization_id,
                    contract_id=wf.id,
                    title=ttl,
                    description=str(dl.get("description") or "")[:500] or None,
                    deliverable_type=str(dl.get("deliverable_type") or "milestone")[:32],
                    project_phase=str(dl.get("project_phase") or "")[:80] or None,
                    owner_name=actor_label(actor),
                    counterparty_owner=ctx["counterparty_name"][:140],
                    due_date=due_str,
                    weight_pct=int(dl.get("weight_pct") or 20),
                    payment_amount=dl.get("payment_amount"),
                    status="not_started",
                )
            )
            added_deliverables += 1

    append_workflow_event(
        wf,
        actor,
        f"Applied contract template: {template.name}",
        f"Mode: {mode} · +{added_terms} key terms · +{added_deliverables} deliverables",
    )
    emit_contract_security_event(
        organization_id=doc.organization_id,
        actor_id=actor.id,
        action="contract.template_applied",
        document_id=doc.id,
    )
    db.session.commit()
    return True, None, {
        "template_id": template.id,
        "template_name": template.name,
        "version": doc.version,
        "added_terms": added_terms,
        "added_deliverables": added_deliverables,
    }


DEFAULT_APPROVED_CLAUSES: list[dict[str, str]] = [
    {
        "name": "Confidentiality & Non-Disclosure",
        "category": "Confidentiality",
        "body": "Each Party shall hold in strict confidence all non-public technical, commercial, financial, and operational information disclosed by the other Party and shall use such information solely for performing its obligations under this Agreement for a period of five (5) years following expiration or termination.",
    },
    {
        "name": "Limitation of Liability",
        "category": "Liability",
        "body": "Except for breaches of confidentiality, willful misconduct, or indemnification obligations, neither Party shall be liable for indirect, incidental, special, or consequential damages, and each Party's aggregate cumulative liability shall not exceed the total fees paid or payable under this Agreement during the twelve (12) months preceding the claim.",
    },
    {
        "name": "Intellectual Property Ownership",
        "category": "IP Rights",
        "body": "Upon receipt of full payment for the applicable deliverables, all right, title, and interest in bespoke work product created specifically for the Client under this Agreement shall vest in the Client. Each Party retains sole ownership of its pre-existing intellectual property and general tools.",
    },
    {
        "name": "Payment Terms & Late Interest",
        "category": "Financial",
        "body": "Undisputed invoices shall be settled within thirty (30) calendar days of receipt via electronic funds transfer. Overdue undisputed amounts shall accrue interest at the lesser of 1.5% per month or the maximum rate permitted by applicable law.",
    },
    {
        "name": "Probation Period & Confirmation",
        "category": "Employment",
        "body": "The Employee's engagement is subject to an initial ninety (90) day probation period with formal 30-, 60-, and 90-day performance reviews. During probation, either Party may terminate this Agreement upon seven (7) days' written notice. Upon written confirmation, the Employee transitions to permanent status.",
    },
    {
        "name": "Suspension & Deliverable Timer Pause",
        "category": "Governance",
        "body": "Either Party may request a formal suspension of performance upon mutual written notice. During any approved SUSPENDED period, active deliverable milestones and SLA timers shall pause automatically and resume with corresponding schedule adjustments upon written resumption notice.",
    },
    {
        "name": "Force Majeure",
        "category": "Risk",
        "body": "Neither Party shall be liable for failure or delay in performance caused by events beyond its reasonable control, including acts of God, war, governmental orders, utility failures, or widespread network outages, provided the affected Party gives prompt written notice and uses commercially reasonable efforts to mitigate impact.",
    },
    {
        "name": "Governing Law & Dispute Resolution",
        "category": "Disputes",
        "body": "This Agreement shall be governed by and construed in accordance with the agreed Governing Law. Any dispute arising out of or in connection with this Agreement shall first be referred to senior executives for good-faith negotiation for fifteen (15) business days before binding arbitration or court proceedings.",
    },
]


def ensure_default_approved_clauses(org_id: int, actor) -> list[dict[str, Any]]:
    """Return approved organization clauses, auto-seeding 8 standard legal clauses if empty."""
    from app.models.clause import Clause, ClauseVersion

    approved_rows = (
        Clause.query.filter_by(organization_id=org_id, state="approved")
        .order_by(Clause.name.asc())
        .limit(80)
        .all()
    )
    if not approved_rows:
        now = datetime.utcnow()
        actor_id = getattr(actor, "id", None)
        if actor_id is not None:
            for item in DEFAULT_APPROVED_CLAUSES:
                existing = Clause.query.filter_by(
                    organization_id=org_id, name=item["name"]
                ).first()
                if existing is not None:
                    if existing.state != "approved":
                        existing.state = "approved"
                        existing.approved_at = now
                        existing.approved_by_id = actor_id
                    continue
                cl = Clause(
                    organization_id=org_id,
                    name=item["name"],
                    category=item["category"],
                    state="approved",
                    created_by_id=actor_id,
                    approved_at=now,
                    approved_by_id=actor_id,
                )
                db.session.add(cl)
                db.session.flush()
                ver = ClauseVersion(
                    clause_id=cl.id,
                    revision=1,
                    body=item["body"],
                    created_by_id=actor_id,
                    approved_at=now,
                    approved_by_id=actor_id,
                )
                db.session.add(ver)
                db.session.flush()
                cl.current_version_id = ver.id
            db.session.commit()
            approved_rows = (
                Clause.query.filter_by(organization_id=org_id, state="approved")
                .order_by(Clause.name.asc())
                .limit(80)
                .all()
            )

    ver_ids = [c.current_version_id for c in approved_rows if c.current_version_id]
    ver_map = (
        {
            v.id: v.body
            for v in ClauseVersion.query.filter(ClauseVersion.id.in_(ver_ids)).all()
        }
        if ver_ids
        else {}
    )
    out = []
    for c in approved_rows:
        body_txt = ver_map.get(c.current_version_id, "")
        if not body_txt and c.versions:
            body_txt = c.versions[-1].body or ""
        out.append({
            "id": c.id,
            "name": c.name,
            "category": c.category or "General",
            "body": body_txt,
        })
    return out


_MONTH_MAP = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}


def _parse_date_to_iso(raw: str) -> str:
    s = (raw or "").strip()
    m_iso = re.search(r"\b(20\d{2}|19\d{2})-(\d{1,2})-(\d{1,2})\b", s)
    if m_iso:
        return f"{int(m_iso.group(1)):04d}-{int(m_iso.group(2)):02d}-{int(m_iso.group(3)):02d}"
    m_mdy = re.search(r"\b([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d{2}|19\d{2})\b", s)
    if m_mdy and m_mdy.group(1).lower() in _MONTH_MAP:
        return f"{int(m_mdy.group(3)):04d}-{_MONTH_MAP[m_mdy.group(1).lower()]:02d}-{int(m_mdy.group(2)):02d}"
    m_dmy = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s+(20\d{2}|19\d{2})\b", s)
    if m_dmy and m_dmy.group(2).lower() in _MONTH_MAP:
        return f"{int(m_dmy.group(3)):04d}-{_MONTH_MAP[m_dmy.group(2).lower()]:02d}-{int(m_dmy.group(1)):02d}"
    return ""


def extract_external_contract_details(file_bytes: bytes, filename: str) -> dict[str, Any]:
    """Extract readable text and structured deal metadata from an uploaded signed PDF/DOCX/TXT."""
    import io as _io
    import zipfile as _zipfile
    import xml.etree.ElementTree as _ET

    fname = (filename or "signed-contract.pdf").strip()
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    orig_sha256 = hashlib.sha256(file_bytes).hexdigest()
    raw_text = ""
    page_count = 1
    pdf_meta_title = ""

    if ext == "pdf" or file_bytes.startswith(b"%PDF-"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(_io.BytesIO(file_bytes))
            page_count = len(reader.pages)
            if reader.metadata and getattr(reader.metadata, "title", None):
                pdf_meta_title = str(reader.metadata.title).strip()
            chunks = []
            for p in reader.pages[:60]:
                t = p.extract_text() or ""
                if t.strip():
                    chunks.append(t.strip())
            raw_text = "\n\n".join(chunks)
        except Exception:
            raw_text = ""
    elif ext == "docx":
        try:
            with _zipfile.ZipFile(_io.BytesIO(file_bytes)) as zf:
                xml_bytes = zf.read("word/document.xml")
            root = _ET.fromstring(xml_bytes)
            paras = []
            for p_el in root.iter():
                if p_el.tag.endswith("}p"):
                    txt = "".join(n.text or "" for n in p_el.iter() if n.tag.endswith("}t")).strip()
                    if txt:
                        paras.append(txt)
            raw_text = "\n".join(paras)
        except Exception:
            raw_text = ""
    else:
        try:
            raw_text = file_bytes.decode("utf-8", errors="ignore")
            raw_text = re.sub(r"<[^>]+>", " ", raw_text)
        except Exception:
            raw_text = ""

    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    low = raw_text.lower()

    # 1. Title
    clean_stem = re.sub(r"[_\-]+", " ", fname.rsplit(".", 1)[0]).strip()
    title = pdf_meta_title or ""
    if not title or title.lower() in ("untitled", "document"):
        for ln in lines[:12]:
            if 6 <= len(ln) <= 120 and any(
                kw in ln.lower()
                for kw in ("agreement", "contract", "statement of work", "sow", "nda", "lease", "memorandum", "deed", "addendum", "amendment")
            ):
                title = ln
                break
    if not title:
        title = clean_stem.title() if clean_stem else "External Signed Contract"
    title = title[:200]

    # 2. Contract Type
    contract_type = "msa"
    if "probation" in low and ("employment" in low or "employee" in low):
        contract_type = "employment_probation"
    elif "statement of work" in low or re.search(r"\bsow\b", low):
        contract_type = "sow"
    elif "non-disclosure" in low or "confidentiality agreement" in low or re.search(r"\bnda\b", low):
        contract_type = "nda"
    elif "employment" in low or "employee" in low:
        contract_type = "employment_permanent"
    elif "lease" in low or "landlord" in low or "tenant" in low:
        contract_type = "commercial_lease"
    elif "vendor" in low or "supply" in low or "procurement" in low:
        contract_type = "vendor_supply"

    # 3. Counterparty / Employee
    counterparty = ""
    m_cp = re.search(
        r"(?:counterparty|client|vendor|supplier|employee|contractor|lessee)\s*[:\-]\s*([A-Z][A-Za-z0-9 &.,'()-]{2,80})",
        raw_text,
        re.I,
    )
    if m_cp:
        counterparty = m_cp.group(1).strip().rstrip(".,;")
    else:
        m_btw = re.search(
            r"between\s+[^,.;]{2,120}?\s+and\s+([A-Z][A-Za-z0-9 &.,'()-]{2,80}?)(?:[,\.\n\(]|effective|dated)",
            raw_text,
            re.I | re.S,
        )
        if m_btw:
            counterparty = re.sub(r"\s+", " ", m_btw.group(1)).strip().rstrip(".,;")

    # 4. Currency & Deal Value
    currency = "USD"
    deal_value = ""
    m_val = re.search(
        r"\b(USD|EUR|GBP|KES|ZAR|UGX|TZS|NGN)\s*([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)",
        raw_text,
    )
    if m_val:
        currency = m_val.group(1).upper()
        deal_value = m_val.group(2)
    else:
        m_sym = re.search(r"(\$|€|£)\s*([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]{1,2})?)", raw_text)
        if m_sym:
            currency = {"$": "USD", "€": "EUR", "£": "GBP"}.get(m_sym.group(1), "USD")
            deal_value = m_sym.group(2)

    # 5. Effective & Expiration Dates
    effective_date = ""
    expiration_date = ""
    m_eff = re.search(
        r"(?:effective(?:\s+date)?|commenc(?:ing|ement)\s+(?:on|date)?|dated(?:\s+as\s+of)?)\s*[:\-]?\s*([A-Za-z0-9,\- ]{6,28})",
        raw_text,
        re.I,
    )
    if m_eff:
        effective_date = _parse_date_to_iso(m_eff.group(1))
    m_exp = re.search(
        r"(?:expir(?:ation|es|y)\s+(?:date|on)?|terminat(?:es|ion\s+date)|end\s+date)\s*[:\-]?\s*([A-Za-z0-9,\- ]{6,28})",
        raw_text,
        re.I,
    )
    if m_exp:
        expiration_date = _parse_date_to_iso(m_exp.group(1))
    if not effective_date:
        all_iso = re.findall(r"\b(?:20\d{2}-\d{2}-\d{2})\b", raw_text)
        if all_iso:
            effective_date = all_iso[0]
            if len(all_iso) > 1 and not expiration_date:
                expiration_date = all_iso[1]

    # 6. Governing Law
    governing_law = ""
    m_law = re.search(
        r"governed\s+by\s+(?:and\s+construed\s+in\s+accordance\s+with\s+)?(?:the\s+)?laws?\s+of\s+(?:the\s+)?([A-Za-z &]{3,60}?)(?:[.,;\n]|without)",
        raw_text,
        re.I,
    )
    if m_law:
        governing_law = m_law.group(1).strip()

    # 7. Probation Period
    probation_days = None
    m_prob = re.search(r"(\d{1,3})\s*(?:-|\s)?days?\s+probation", raw_text, re.I)
    if m_prob:
        probation_days = int(m_prob.group(1))
    else:
        m_prob_m = re.search(r"(\d{1,2})\s*(?:-|\s)?months?\s+probation", raw_text, re.I)
        if m_prob_m:
            probation_days = int(m_prob_m.group(1)) * 30

    # 8. Signatories
    signatories = []
    for m_sig in re.finditer(
        r"(?:signed\s+by|authorized\s+signatory|signatory|name)\s*[:\-]\s*([A-Z][A-Za-z .'-]{2,50})",
        raw_text,
        re.I,
    ):
        nm = m_sig.group(1).strip().rstrip(".,;:")
        if nm and nm not in signatories and len(signatories) < 6:
            signatories.append(nm)

    # 9. Clean HTML representation for Contract Studio viewer
    body_paras = []
    for ln in lines[:120]:
        esc_ln = html_std.escape(ln)
        if len(ln) <= 90 and (ln.isupper() or re.match(r"^\d+\.\s+[A-Z]", ln)):
            body_paras.append(f"<h2>{esc_ln}</h2>")
        else:
            body_paras.append(f"<p>{esc_ln}</p>")
    html_body = (
        f"<h1>{html_std.escape(title)}</h1>"
        + ("".join(body_paras) if body_paras else "<p>External signed contract archived in TrustSeal Vault. Open PDF preview to view the original signed document.</p>")
    )

    return {
        "filename": fname,
        "file_size": len(file_bytes),
        "page_count": page_count,
        "sha256": orig_sha256,
        "title": title,
        "contract_type": contract_type,
        "counterparty_name": counterparty,
        "currency": currency,
        "deal_value": deal_value,
        "effective_date": effective_date,
        "expiration_date": expiration_date,
        "governing_law": governing_law,
        "probation_days": probation_days,
        "signatories": signatories,
        "text_snippet": raw_text[:800],
        "html_body": html_body,
        "is_pdf": bool(ext == "pdf" or file_bytes.startswith(b"%PDF-")),
    }


def file_external_signed_contract(
    *,
    file_bytes: bytes,
    filename: str,
    project: Project,
    actor,
    meta: dict[str, Any] | None = None,
) -> tuple[TSDocument, ContractWorkflow]:
    """Archive an already-signed external contract into the encrypted .tsd Vault with EvidenceRetention."""
    import base64

    extracted = extract_external_contract_details(file_bytes, filename)
    m = meta or {}
    now = datetime.utcnow()
    now_str = now.strftime("%Y-%m-%d %H:%M UTC")

    title = (str(m.get("title") or "").strip() or extracted["title"])[:255]
    contract_type = (str(m.get("contract_type") or "").strip() or extracted["contract_type"])[:48]
    counterparty = (str(m.get("counterparty_name") or "").strip() or extracted["counterparty_name"])[:200]
    currency = (str(m.get("currency") or "").strip() or extracted["currency"] or "USD")[:12]
    deal_value = (str(m.get("deal_value") or "").strip() or extracted["deal_value"])[:64] or None
    eff_date = (str(m.get("effective_date") or "").strip() or extracted["effective_date"])[:32] or None
    exp_date = (str(m.get("expiration_date") or "").strip() or extracted["expiration_date"])[:32] or None
    gov_law = (str(m.get("governing_law") or "").strip() or extracted["governing_law"])[:120] or None
    notes = str(m.get("notes") or "").strip()[:500]
    req_status = str(m.get("contract_status") or "SIGNED").strip().upper()
    if req_status not in ("DRAFT", "SIGNED", "SUSPENDED", "TERMINATED"):
        req_status = "SIGNED"

    raw_sigs = m.get("signatories")
    sig_names: list[str] = []
    if isinstance(raw_sigs, list):
        sig_names = [str(x).strip() for x in raw_sigs if str(x).strip()]
    elif isinstance(raw_sigs, str) and raw_sigs.strip():
        sig_names = [x.strip() for x in raw_sigs.split(",") if x.strip()]
    else:
        sig_names = extracted["signatories"]
    if not sig_names:
        sig_names = [actor_label(actor)]
        if counterparty:
            sig_names.append(counterparty)

    signers_json = [
        {
            "id": f"ext-sig-{idx + 1}",
            "order": idx + 1,
            "name": nm[:120],
            "email": "",
            "role": "External Executed Signatory",
            "status": "signed" if req_status != "DRAFT" else "pending",
            "signed_at": (eff_date or now_str) if req_status != "DRAFT" else "",
            "signature_text": nm[:120],
            "signature_svg": "",
        }
        for idx, nm in enumerate(sig_names[:8])
    ]

    extras: dict[str, Any] = {
        "source": "external_upload",
        "external_filename": extracted["filename"],
        "external_sha256": extracted["sha256"],
        "external_page_count": extracted["page_count"],
        "project_id": project.id,
    }
    if extracted["is_pdf"]:
        extras["external_original_pdf_b64"] = base64.b64encode(file_bytes).decode("ascii")

    env = pack_content(
        html=sanitize_html(extracted["html_body"]),
        description=f"Filed external signed contract ({extracted['filename']}) under {project.project_code}",
        extras=extras,
    )
    ct = encrypt_content_envelope(env, organization_id=project.organization_id)
    doc = TSDocument(
        organization_id=project.organization_id,
        created_by_id=actor.id,
        title=title,
        description=f"External Filed Contract · {extracted['filename']}" + (f" · {notes}" if notes else ""),
        export_policy="pdf_allowed",
        status="finalized" if req_status != "DRAFT" else "draft",
        ciphertext=ct,
        ciphertext_sha256=sha256_hex(ct),
        plaintext_bytes=len(env),
        version=1,
    )
    db.session.add(doc)
    db.session.flush()

    wf = ContractWorkflow(
        organization_id=project.organization_id,
        document_id=doc.id,
        project_id=project.id,
        contract_number=f"EXT-{now.year}-{doc.id:04d}",
        contract_type=contract_type,
        contract_status=req_status,
        stage="signed" if req_status != "DRAFT" else "draft",
        edit_locked=(req_status != "DRAFT"),
        closed_at=now if req_status != "DRAFT" else None,
        execution_sha256=extracted["sha256"],
        counterparty_name=counterparty or None,
        deal_value=deal_value,
        currency=currency,
        effective_date=eff_date,
        expiration_date=exp_date,
        governing_law=gov_law,
        signers_json=signers_json,
        checklist_json={
            "commercial_terms": True,
            "liability_indemnity": True,
            "confidentiality_data": True,
            "governing_law": True,
        },
        events_json=[
            {
                "at": now_str,
                "actor": actor_label(actor),
                "action": "Filed External Signed Contract",
                "detail": f"File: {extracted['filename']} · SHA-256 {extracted['sha256'][:16]}… · Project: {project.project_code}"
                + (f" · {notes}" if notes else ""),
            }
        ],
    )
    db.session.add(wf)
    db.session.flush()

    # Preserve in Evidence & Retention Vault
    if req_status != "DRAFT":
        retention = EvidenceRetention(
            organization_id=project.organization_id,
            artifact_type="finalized_pdf",
            artifact_id=doc.id,
            artifact_sha256=extracted["sha256"],
            retain_until=now + timedelta(days=365 * 7),
            created_by_id=actor.id,
        )
        db.session.add(retention)
        db.session.flush()
        wf.evidence_retention_id = retention.id

    # Auto-seed Probation Key Term if detected or supplied
    prob_days = m.get("probation_days") or extracted.get("probation_days")
    if prob_days:
        try:
            p_int = int(prob_days)
            base_dt = datetime.strptime(eff_date[:10], "%Y-%m-%d") if eff_date else now
            db.session.add(
                ContractKeyTerm(
                    organization_id=project.organization_id,
                    contract_id=wf.id,
                    category="probation",
                    term_key="probation_period",
                    label=f"{p_int}-Day Probation Period",
                    value_text=f"{p_int} calendar days (extracted from filed contract)",
                    numeric_value=p_int,
                    unit="days",
                    start_date=base_dt.strftime("%Y-%m-%d"),
                    end_date=(base_dt + timedelta(days=p_int)).strftime("%Y-%m-%d"),
                    alert_days_before=14,
                    status="active",
                )
            )
        except Exception:
            pass

    emit_contract_security_event(
        organization_id=project.organization_id,
        actor_id=actor.id,
        action="contract.external_filed",
        document_id=doc.id,
    )
    emit_contract_outbox(
        organization_id=project.organization_id,
        event_type="contract.external_filed",
        document_id=doc.id,
        payload={
            "document_id": doc.id,
            "contract_number": wf.contract_number,
            "contract_status": wf.contract_status,
            "filename": extracted["filename"],
            "original_sha256": extracted["sha256"],
            "evidence_retention_id": wf.evidence_retention_id,
        },
    )
    db.session.commit()
    return doc, wf
