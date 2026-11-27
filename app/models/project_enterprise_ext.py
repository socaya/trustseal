"""Batch 2 Enterprise Project Management models (PM-05, 09, 11, 14, 17, 21, 22, 24, 26, 30).

Complements ``app/models/project_management.py`` with:
- PM-05: ``ProjectRequirement`` (versioned scope/requirements traceability)
- PM-09: ``ProjectSprint`` & ``ProjectBacklogItem`` (agile & hybrid delivery)
- PM-11: ``OrgResourceProfile`` (organization-wide resource pool & skills)
- PM-14: ``ProjectAssetBooking`` (equipment, materials & logistics custody)
- PM-17: ``ProjectProcurement`` (requisition -> RFQ -> award with SoD & cost commitment)
- PM-21: ``ProjectQualityRecord`` (inspections, tests, defects, CAPA)
- PM-22: ``ProjectStakeholder`` (stakeholder influence/interest & comms plan)
- PM-24: ``ProjectDocumentLink`` (pinned immutable TSD version links)
- PM-26: ``ProjectIndicator`` & ``ProjectIndicatorObservation`` (M&E logframe)
- PM-30: ``ProjectClosureItem`` & ``ProjectBenefit`` (handover, closure & benefits)
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from app.extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# =====================================================================
# PM-05: SCOPE & REQUIREMENTS TRACEABILITY
# =====================================================================

class ProjectRequirement(db.Model):
    __tablename__ = "project_requirements"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    req_code = db.Column(db.String(40), nullable=False)
    title = db.Column(db.String(220), nullable=False)
    category = db.Column(db.String(32), nullable=False, default="business")  # business, technical, regulatory, security
    priority = db.Column(db.String(16), nullable=False, default="must")      # must, should, could
    acceptance_criteria = db.Column(db.Text, nullable=True)
    wbs_node_id = db.Column(db.Integer, db.ForeignKey("project_wbs_nodes.id"), nullable=True)
    linked_task_id = db.Column(db.Integer, db.ForeignKey("project_tasks.id"), nullable=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(24), nullable=False, default="draft")       # draft, approved, verified, superseded
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "req_code": self.req_code,
            "title": self.title,
            "category": self.category or "business",
            "priority": self.priority or "must",
            "acceptance_criteria": self.acceptance_criteria or "",
            "wbs_node_id": self.wbs_node_id,
            "linked_task_id": self.linked_task_id,
            "version": int(self.version or 1),
            "status": self.status or "draft",
            "approved_at": self.approved_at.strftime("%Y-%m-%d %H:%M UTC") if self.approved_at else "",
        }


# =====================================================================
# PM-09: AGILE & HYBRID DELIVERY (SPRINTS & BACKLOG)
# =====================================================================

class ProjectSprint(db.Model):
    __tablename__ = "project_sprints"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    goal = db.Column(db.String(300), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    capacity_points = db.Column(db.Integer, nullable=False, default=30)
    completed_points = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(24), nullable=False, default="planned")  # planned, active, completed
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "goal": self.goal or "",
            "start_date": self.start_date.isoformat() if self.start_date else "",
            "end_date": self.end_date.isoformat() if self.end_date else "",
            "capacity_points": int(self.capacity_points or 0),
            "completed_points": int(self.completed_points or 0),
            "status": self.status or "planned",
        }


class ProjectBacklogItem(db.Model):
    __tablename__ = "project_backlog_items"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    sprint_id = db.Column(db.Integer, db.ForeignKey("project_sprints.id"), nullable=True, index=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey("project_requirements.id"), nullable=True)
    item_type = db.Column(db.String(24), nullable=False, default="story")  # epic, story, defect, chore
    title = db.Column(db.String(220), nullable=False)
    story_points = db.Column(db.Integer, nullable=False, default=3)
    priority = db.Column(db.String(16), nullable=False, default="medium")
    status = db.Column(db.String(24), nullable=False, default="backlog")   # backlog, ready, in_progress, done
    assignee_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "sprint_id": self.sprint_id,
            "requirement_id": self.requirement_id,
            "item_type": self.item_type or "story",
            "title": self.title,
            "story_points": int(self.story_points or 0),
            "priority": self.priority or "medium",
            "status": self.status or "backlog",
            "assignee_user_id": self.assignee_user_id,
        }


# =====================================================================
# PM-11: ORGANIZATION RESOURCE POOL & SKILLS
# =====================================================================

class OrgResourceProfile(db.Model):
    __tablename__ = "org_resource_profiles"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    display_name = db.Column(db.String(160), nullable=False)
    resource_type = db.Column(db.String(24), nullable=False, default="employee")  # employee, consultant, contractor, equipment, facility
    department = db.Column(db.String(120), nullable=True)
    skills_csv = db.Column(db.String(400), nullable=True)
    certification_name = db.Column(db.String(160), nullable=True)
    certification_expiry_date = db.Column(db.Date, nullable=True)
    standard_hourly_rate = db.Column(db.Numeric(12, 2), nullable=True)
    currency = db.Column(db.String(12), nullable=False, default="USD")
    availability_pct = db.Column(db.Integer, nullable=False, default=100)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    def is_certification_expired(self, today: date | None = None) -> bool:
        if not self.certification_expiry_date:
            return False
        return self.certification_expiry_date < (today or date.today())

    def to_dict(self, include_rates: bool = False) -> dict[str, Any]:
        out = {
            "id": self.id,
            "user_id": self.user_id,
            "display_name": self.display_name,
            "resource_type": self.resource_type or "employee",
            "department": self.department or "",
            "skills": [s.strip() for s in (self.skills_csv or "").split(",") if s.strip()],
            "certification_name": self.certification_name or "",
            "certification_expiry_date": self.certification_expiry_date.isoformat() if self.certification_expiry_date else "",
            "certification_expired": self.is_certification_expired(),
            "availability_pct": int(self.availability_pct or 100),
            "is_active": bool(self.is_active),
        }
        if include_rates:
            out["standard_hourly_rate"] = str(self.standard_hourly_rate) if self.standard_hourly_rate is not None else None
            out["currency"] = self.currency or "USD"
        return out


# =====================================================================
# PM-14: EQUIPMENT, MATERIALS & LOGISTICS
# =====================================================================

class ProjectAssetBooking(db.Model):
    __tablename__ = "project_asset_bookings"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    asset_name = db.Column(db.String(180), nullable=False)
    asset_type = db.Column(db.String(24), nullable=False, default="equipment")  # equipment, vehicle, material, facility
    exclusive = db.Column(db.Boolean, nullable=False, default=True)
    quantity = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("1.00"))
    unit = db.Column(db.String(24), nullable=False, default="unit")
    unit_cost = db.Column(db.Numeric(12, 2), nullable=True)
    currency = db.Column(db.String(12), nullable=False, default="USD")
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    custodian_name = db.Column(db.String(140), nullable=True)
    status = db.Column(db.String(24), nullable=False, default="booked")  # booked, issued, returned, consumed
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "asset_name": self.asset_name,
            "asset_type": self.asset_type or "equipment",
            "exclusive": bool(self.exclusive),
            "quantity": str(self.quantity or Decimal("1.00")),
            "unit": self.unit or "unit",
            "unit_cost": str(self.unit_cost) if self.unit_cost is not None else None,
            "currency": self.currency or "USD",
            "start_date": self.start_date.isoformat() if self.start_date else "",
            "end_date": self.end_date.isoformat() if self.end_date else "",
            "custodian_name": self.custodian_name or "",
            "status": self.status or "booked",
        }


# =====================================================================
# PM-17: PROCUREMENT & SUPPLIER MANAGEMENT
# =====================================================================

class ProjectProcurement(db.Model):
    __tablename__ = "project_procurements"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    req_number = db.Column(db.String(40), nullable=False)
    title = db.Column(db.String(220), nullable=False)
    supplier_name = db.Column(db.String(180), nullable=True)
    estimated_amount = db.Column(db.Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    awarded_amount = db.Column(db.Numeric(18, 2), nullable=True)
    currency = db.Column(db.String(12), nullable=False, default="USD")
    contract_id = db.Column(db.Integer, db.ForeignKey("contract_workflows.id"), nullable=True)
    commitment_cost_event_id = db.Column(db.Integer, db.ForeignKey("project_cost_events.id"), nullable=True)
    status = db.Column(db.String(24), nullable=False, default="requisition")  # requisition, rfq, evaluated, awarded, received, closed
    requested_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    awarded_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "req_number": self.req_number,
            "title": self.title,
            "supplier_name": self.supplier_name or "",
            "estimated_amount": str(self.estimated_amount or Decimal("0.00")),
            "awarded_amount": str(self.awarded_amount) if self.awarded_amount is not None else None,
            "currency": self.currency or "USD",
            "contract_id": self.contract_id,
            "commitment_cost_event_id": self.commitment_cost_event_id,
            "status": self.status or "requisition",
            "requested_by_id": self.requested_by_id,
            "approved_by_id": self.approved_by_id,
        }


# =====================================================================
# PM-21: QUALITY MANAGEMENT & ASSURANCE
# =====================================================================

class ProjectQualityRecord(db.Model):
    __tablename__ = "project_quality_records"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    record_type = db.Column(db.String(24), nullable=False, default="inspection")  # inspection, test, defect, capa
    title = db.Column(db.String(220), nullable=False)
    severity = db.Column(db.String(16), nullable=False, default="medium")
    wbs_node_id = db.Column(db.Integer, db.ForeignKey("project_wbs_nodes.id"), nullable=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey("project_requirements.id"), nullable=True)
    reviewer_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    evidence_notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(24), nullable=False, default="open")  # open, passed, failed, resolved, verified
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "record_type": self.record_type or "inspection",
            "title": self.title,
            "severity": self.severity or "medium",
            "wbs_node_id": self.wbs_node_id,
            "requirement_id": self.requirement_id,
            "reviewer_user_id": self.reviewer_user_id,
            "evidence_notes": self.evidence_notes or "",
            "status": self.status or "open",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
        }


# =====================================================================
# PM-22: STAKEHOLDER & COMMUNICATION MANAGEMENT
# =====================================================================

class ProjectStakeholder(db.Model):
    __tablename__ = "project_stakeholders"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    organization_name = db.Column(db.String(160), nullable=True)
    role_title = db.Column(db.String(120), nullable=True)
    email = db.Column(db.String(180), nullable=True)
    influence_level = db.Column(db.String(16), nullable=False, default="medium")  # low, medium, high
    interest_level = db.Column(db.String(16), nullable=False, default="medium")
    comms_cadence = db.Column(db.String(24), nullable=False, default="monthly")
    engagement_strategy = db.Column(db.String(240), nullable=True)
    is_external = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "organization_name": self.organization_name or "",
            "role_title": self.role_title or "",
            "email": self.email or "",
            "influence_level": self.influence_level or "medium",
            "interest_level": self.interest_level or "medium",
            "comms_cadence": self.comms_cadence or "monthly",
            "engagement_strategy": self.engagement_strategy or "",
            "is_external": bool(self.is_external),
        }


# =====================================================================
# PM-24: DOCUMENTS & RECORDS LINK (PINNED IMMUTABLE TSD VERSIONS)
# =====================================================================

class ProjectDocumentLink(db.Model):
    __tablename__ = "project_document_links"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    document_id = db.Column(db.Integer, db.ForeignKey("ts_documents.id"), nullable=False, index=True)
    pinned_version = db.Column(db.Integer, nullable=False, default=1)
    classification = db.Column(db.String(32), nullable=False, default="deliverable")  # charter, plan, deliverable, certificate, evidence, report
    retention_rule = db.Column(db.String(64), nullable=True, default="7_years")
    linked_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        db.UniqueConstraint("project_id", "document_id", "pinned_version", name="uq_proj_doc_ver"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "document_id": self.document_id,
            "pinned_version": int(self.pinned_version or 1),
            "classification": self.classification or "deliverable",
            "retention_rule": self.retention_rule or "7_years",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
        }


# =====================================================================
# PM-26: MONITORING, EVALUATION & RESULTS FRAMEWORK (M&E)
# =====================================================================

class ProjectIndicator(db.Model):
    __tablename__ = "project_indicators"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    indicator_code = db.Column(db.String(40), nullable=False)
    level = db.Column(db.String(24), nullable=False, default="output")  # input, output, outcome, impact
    title = db.Column(db.String(220), nullable=False)
    unit = db.Column(db.String(32), nullable=False, default="count")
    baseline_value = db.Column(db.Numeric(14, 2), nullable=True)
    target_value = db.Column(db.Numeric(14, 2), nullable=True)
    owner_name = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "indicator_code": self.indicator_code,
            "level": self.level or "output",
            "title": self.title,
            "unit": self.unit or "count",
            "baseline_value": str(self.baseline_value) if self.baseline_value is not None else None,
            "target_value": str(self.target_value) if self.target_value is not None else None,
            "owner_name": self.owner_name or "",
        }


class ProjectIndicatorObservation(db.Model):
    __tablename__ = "project_indicator_observations"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    indicator_id = db.Column(db.Integer, db.ForeignKey("project_indicators.id"), nullable=False, index=True)
    period_label = db.Column(db.String(40), nullable=False)  # e.g., 2026-Q4
    numerator = db.Column(db.Numeric(14, 2), nullable=True)
    denominator = db.Column(db.Numeric(14, 2), nullable=True)
    observed_value = db.Column(db.Numeric(14, 2), nullable=False)
    evidence_note = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(24), nullable=False, default="draft")  # draft, validated, rejected
    validated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    validated_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        db.UniqueConstraint("indicator_id", "period_label", name="uq_indicator_period"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "indicator_id": self.indicator_id,
            "period_label": self.period_label,
            "numerator": str(self.numerator) if self.numerator is not None else None,
            "denominator": str(self.denominator) if self.denominator is not None else None,
            "observed_value": str(self.observed_value),
            "evidence_note": self.evidence_note or "",
            "status": self.status or "draft",
        }


# =====================================================================
# PM-30: HANDOVER, CLOSURE & BENEFITS REALIZATION
# =====================================================================

class ProjectClosureItem(db.Model):
    __tablename__ = "project_closure_items"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    category = db.Column(db.String(32), nullable=False, default="handover")  # handover, financial, contractual, lessons
    title = db.Column(db.String(220), nullable=False)
    is_mandatory = db.Column(db.Boolean, nullable=False, default=True)
    completed = db.Column(db.Boolean, nullable=False, default=False)
    evidence_note = db.Column(db.Text, nullable=True)
    completed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "category": self.category or "handover",
            "title": self.title,
            "is_mandatory": bool(self.is_mandatory),
            "completed": bool(self.completed),
            "evidence_note": self.evidence_note or "",
            "completed_at": self.completed_at.strftime("%Y-%m-%d %H:%M UTC") if self.completed_at else "",
        }


class ProjectBenefit(db.Model):
    __tablename__ = "project_benefits"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    benefit_type = db.Column(db.String(24), nullable=False, default="operational")  # financial, operational, social, compliance
    title = db.Column(db.String(220), nullable=False)
    target_value = db.Column(db.String(120), nullable=True)
    realized_value = db.Column(db.String(120), nullable=True)
    review_date = db.Column(db.Date, nullable=True)
    owner_name = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(24), nullable=False, default="planned")  # planned, tracking, realized, partial
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "benefit_type": self.benefit_type or "operational",
            "title": self.title,
            "target_value": self.target_value or "",
            "realized_value": self.realized_value or "",
            "review_date": self.review_date.isoformat() if self.review_date else "",
            "owner_name": self.owner_name or "",
            "status": self.status or "planned",
        }
