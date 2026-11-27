"""Enterprise Project Management Batch 2 schema (PM-05, 09, 11, 14, 17, 21, 22, 24, 26, 30).

Revision ID: c3d4e5f6a705
Revises: b2c3d4e5f604
Create Date: 2026-11-27 05:45:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c3d4e5f6a705"
down_revision = "b2c3d4e5f604"
branch_labels = None
depends_on = None


def _exists(insp, name: str) -> bool:
    return name in insp.get_table_names()


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not _exists(insp, "project_requirements"):
        op.create_table(
            "project_requirements",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("req_code", sa.String(40), nullable=False),
            sa.Column("title", sa.String(220), nullable=False),
            sa.Column("category", sa.String(32), nullable=False, server_default="business"),
            sa.Column("priority", sa.String(16), nullable=False, server_default="must"),
            sa.Column("acceptance_criteria", sa.Text(), nullable=True),
            sa.Column("wbs_node_id", sa.Integer(), sa.ForeignKey("project_wbs_nodes.id"), nullable=True),
            sa.Column("linked_task_id", sa.Integer(), sa.ForeignKey("project_tasks.id"), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
            sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_project_requirements_project", "project_requirements", ["project_id"])

    if not _exists(insp, "project_sprints"):
        op.create_table(
            "project_sprints",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("goal", sa.String(300), nullable=True),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("capacity_points", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("completed_points", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(24), nullable=False, server_default="planned"),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_project_sprints_project", "project_sprints", ["project_id"])

    if not _exists(insp, "project_backlog_items"):
        op.create_table(
            "project_backlog_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("sprint_id", sa.Integer(), sa.ForeignKey("project_sprints.id"), nullable=True),
            sa.Column("requirement_id", sa.Integer(), sa.ForeignKey("project_requirements.id"), nullable=True),
            sa.Column("item_type", sa.String(24), nullable=False, server_default="story"),
            sa.Column("title", sa.String(220), nullable=False),
            sa.Column("story_points", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("priority", sa.String(16), nullable=False, server_default="medium"),
            sa.Column("status", sa.String(24), nullable=False, server_default="backlog"),
            sa.Column("assignee_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_project_backlog_project", "project_backlog_items", ["project_id"])

    if not _exists(insp, "org_resource_profiles"):
        op.create_table(
            "org_resource_profiles",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("display_name", sa.String(160), nullable=False),
            sa.Column("resource_type", sa.String(24), nullable=False, server_default="employee"),
            sa.Column("department", sa.String(120), nullable=True),
            sa.Column("skills_csv", sa.String(400), nullable=True),
            sa.Column("certification_name", sa.String(160), nullable=True),
            sa.Column("certification_expiry_date", sa.Date(), nullable=True),
            sa.Column("standard_hourly_rate", sa.Numeric(12, 2), nullable=True),
            sa.Column("currency", sa.String(12), nullable=False, server_default="USD"),
            sa.Column("availability_pct", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_org_resource_profiles_org", "org_resource_profiles", ["organization_id"])

    if not _exists(insp, "project_asset_bookings"):
        op.create_table(
            "project_asset_bookings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("asset_name", sa.String(180), nullable=False),
            sa.Column("asset_type", sa.String(24), nullable=False, server_default="equipment"),
            sa.Column("exclusive", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("quantity", sa.Numeric(10, 2), nullable=False, server_default="1.00"),
            sa.Column("unit", sa.String(24), nullable=False, server_default="unit"),
            sa.Column("unit_cost", sa.Numeric(12, 2), nullable=True),
            sa.Column("currency", sa.String(12), nullable=False, server_default="USD"),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=False),
            sa.Column("custodian_name", sa.String(140), nullable=True),
            sa.Column("status", sa.String(24), nullable=False, server_default="booked"),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_project_asset_bookings_project", "project_asset_bookings", ["project_id"])

    if not _exists(insp, "project_procurements"):
        op.create_table(
            "project_procurements",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("req_number", sa.String(40), nullable=False),
            sa.Column("title", sa.String(220), nullable=False),
            sa.Column("supplier_name", sa.String(180), nullable=True),
            sa.Column("estimated_amount", sa.Numeric(18, 2), nullable=False, server_default="0.00"),
            sa.Column("awarded_amount", sa.Numeric(18, 2), nullable=True),
            sa.Column("currency", sa.String(12), nullable=False, server_default="USD"),
            sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contract_workflows.id"), nullable=True),
            sa.Column("commitment_cost_event_id", sa.Integer(), sa.ForeignKey("project_cost_events.id"), nullable=True),
            sa.Column("status", sa.String(24), nullable=False, server_default="requisition"),
            sa.Column("requested_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("awarded_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_project_procurements_project", "project_procurements", ["project_id"])

    if not _exists(insp, "project_quality_records"):
        op.create_table(
            "project_quality_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("record_type", sa.String(24), nullable=False, server_default="inspection"),
            sa.Column("title", sa.String(220), nullable=False),
            sa.Column("severity", sa.String(16), nullable=False, server_default="medium"),
            sa.Column("wbs_node_id", sa.Integer(), sa.ForeignKey("project_wbs_nodes.id"), nullable=True),
            sa.Column("requirement_id", sa.Integer(), sa.ForeignKey("project_requirements.id"), nullable=True),
            sa.Column("reviewer_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("evidence_notes", sa.Text(), nullable=True),
            sa.Column("status", sa.String(24), nullable=False, server_default="open"),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_project_quality_project", "project_quality_records", ["project_id"])

    if not _exists(insp, "project_stakeholders"):
        op.create_table(
            "project_stakeholders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("organization_name", sa.String(160), nullable=True),
            sa.Column("role_title", sa.String(120), nullable=True),
            sa.Column("email", sa.String(180), nullable=True),
            sa.Column("influence_level", sa.String(16), nullable=False, server_default="medium"),
            sa.Column("interest_level", sa.String(16), nullable=False, server_default="medium"),
            sa.Column("comms_cadence", sa.String(24), nullable=False, server_default="monthly"),
            sa.Column("engagement_strategy", sa.String(240), nullable=True),
            sa.Column("is_external", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_project_stakeholders_project", "project_stakeholders", ["project_id"])

    if not _exists(insp, "project_document_links"):
        op.create_table(
            "project_document_links",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("ts_documents.id"), nullable=False),
            sa.Column("pinned_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("classification", sa.String(32), nullable=False, server_default="deliverable"),
            sa.Column("retention_rule", sa.String(64), nullable=True, server_default="7_years"),
            sa.Column("linked_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("project_id", "document_id", "pinned_version", name="uq_proj_doc_ver"),
        )
        op.create_index("ix_project_doc_links_project", "project_document_links", ["project_id"])

    if not _exists(insp, "project_indicators"):
        op.create_table(
            "project_indicators",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("indicator_code", sa.String(40), nullable=False),
            sa.Column("level", sa.String(24), nullable=False, server_default="output"),
            sa.Column("title", sa.String(220), nullable=False),
            sa.Column("unit", sa.String(32), nullable=False, server_default="count"),
            sa.Column("baseline_value", sa.Numeric(14, 2), nullable=True),
            sa.Column("target_value", sa.Numeric(14, 2), nullable=True),
            sa.Column("owner_name", sa.String(120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_project_indicators_project", "project_indicators", ["project_id"])

    if not _exists(insp, "project_indicator_observations"):
        op.create_table(
            "project_indicator_observations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("indicator_id", sa.Integer(), sa.ForeignKey("project_indicators.id"), nullable=False),
            sa.Column("period_label", sa.String(40), nullable=False),
            sa.Column("numerator", sa.Numeric(14, 2), nullable=True),
            sa.Column("denominator", sa.Numeric(14, 2), nullable=True),
            sa.Column("observed_value", sa.Numeric(14, 2), nullable=False),
            sa.Column("evidence_note", sa.Text(), nullable=True),
            sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
            sa.Column("validated_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("indicator_id", "period_label", name="uq_indicator_period"),
        )
        op.create_index("ix_project_ind_obs_indicator", "project_indicator_observations", ["indicator_id"])

    if not _exists(insp, "project_closure_items"):
        op.create_table(
            "project_closure_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("category", sa.String(32), nullable=False, server_default="handover"),
            sa.Column("title", sa.String(220), nullable=False),
            sa.Column("is_mandatory", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("completed", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("evidence_note", sa.Text(), nullable=True),
            sa.Column("completed_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_project_closure_project", "project_closure_items", ["project_id"])

    if not _exists(insp, "project_benefits"):
        op.create_table(
            "project_benefits",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("benefit_type", sa.String(24), nullable=False, server_default="operational"),
            sa.Column("title", sa.String(220), nullable=False),
            sa.Column("target_value", sa.String(120), nullable=True),
            sa.Column("realized_value", sa.String(120), nullable=True),
            sa.Column("review_date", sa.Date(), nullable=True),
            sa.Column("owner_name", sa.String(120), nullable=True),
            sa.Column("status", sa.String(24), nullable=False, server_default="planned"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_project_benefits_project", "project_benefits", ["project_id"])


def downgrade():
    for tbl in (
        "project_benefits",
        "project_closure_items",
        "project_indicator_observations",
        "project_indicators",
        "project_document_links",
        "project_stakeholders",
        "project_quality_records",
        "project_procurements",
        "project_asset_bookings",
        "org_resource_profiles",
        "project_backlog_items",
        "project_sprints",
        "project_requirements",
    ):
        op.drop_table(tbl)
