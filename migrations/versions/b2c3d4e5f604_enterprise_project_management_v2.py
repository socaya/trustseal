"""Enterprise Project Management Module v2.0 schema.

Revision ID: b2c3d4e5f604
Revises: a1b2c3d4e603
Create Date: 2026-11-26 23:45:00.000000

Adds:
- Portfolios, Programmes, Demand Intakes
- Charters, Stage Gates, WBS Nodes, Task Dependencies
- Resource Allocations, Timesheets, Decimal Budget Lines & Cost Events
- Integrated Change Requests & Project Memberships
- Additive typed columns on projects, project_tasks & project_risks (idempotent)
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b2c3d4e5f604"
down_revision = "a1b2c3d4e603"
branch_labels = None
depends_on = None


def _table_exists(inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _col_exists(inspector, table: str, col: str) -> bool:
    if not _table_exists(inspector, table):
        return False
    return any(c["name"] == col for c in inspector.get_columns(table))


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. Portfolios (PM-02)
    if not _table_exists(insp, "project_portfolios"):
        op.create_table(
            "project_portfolios",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("code", sa.String(40), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("strategic_objective", sa.String(300), nullable=True),
            sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("budget_ceiling", sa.Numeric(18, 2), nullable=True),
            sa.Column("currency", sa.String(12), nullable=False, server_default="USD"),
            sa.Column("status", sa.String(24), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("organization_id", "code", name="uq_portfolio_org_code"),
        )
        op.create_index("ix_project_portfolios_org", "project_portfolios", ["organization_id"])

    # 2. Programmes (PM-03)
    if not _table_exists(insp, "project_programmes"):
        op.create_table(
            "project_programmes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("portfolio_id", sa.Integer(), sa.ForeignKey("project_portfolios.id"), nullable=True),
            sa.Column("code", sa.String(40), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("sponsor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("manager_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("budget_ceiling", sa.Numeric(18, 2), nullable=True),
            sa.Column("currency", sa.String(12), nullable=False, server_default="USD"),
            sa.Column("target_end_date", sa.Date(), nullable=True),
            sa.Column("status", sa.String(24), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("organization_id", "code", name="uq_programme_org_code"),
        )
        op.create_index("ix_project_programmes_org", "project_programmes", ["organization_id"])

    # 3. Additive typed columns on projects
    if _table_exists(insp, "projects"):
        for col_name, col_def in (
            ("lifecycle_state", sa.Column("lifecycle_state", sa.String(32), nullable=False, server_default="executing")),
            ("delivery_methodology", sa.Column("delivery_methodology", sa.String(24), nullable=False, server_default="hybrid")),
            ("portfolio_id", sa.Column("portfolio_id", sa.Integer(), sa.ForeignKey("project_portfolios.id"), nullable=True)),
            ("programme_id", sa.Column("programme_id", sa.Integer(), sa.ForeignKey("project_programmes.id"), nullable=True)),
            ("sponsor_user_id", sa.Column("sponsor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True)),
            ("confidentiality", sa.Column("confidentiality", sa.String(24), nullable=False, server_default="internal")),
            ("budget_numeric", sa.Column("budget_numeric", sa.Numeric(18, 2), nullable=True)),
            ("start_date_typed", sa.Column("start_date_typed", sa.Date(), nullable=True)),
            ("end_date_typed", sa.Column("end_date_typed", sa.Date(), nullable=True)),
            ("version", sa.Column("version", sa.Integer(), nullable=False, server_default="1")),
        ):
            if not _col_exists(insp, "projects", col_name):
                op.add_column("projects", col_def)

    # 4. Demand & Intake (PM-01)
    if not _table_exists(insp, "project_intakes"):
        op.create_table(
            "project_intakes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("intake_code", sa.String(40), nullable=False),
            sa.Column("title", sa.String(220), nullable=False),
            sa.Column("problem_statement", sa.Text(), nullable=True),
            sa.Column("strategic_alignment", sa.String(240), nullable=True),
            sa.Column("category", sa.String(48), nullable=False, server_default="client_delivery"),
            sa.Column("delivery_methodology", sa.String(24), nullable=False, server_default="hybrid"),
            sa.Column("portfolio_id", sa.Integer(), sa.ForeignKey("project_portfolios.id"), nullable=True),
            sa.Column("programme_id", sa.Integer(), sa.ForeignKey("project_programmes.id"), nullable=True),
            sa.Column("sponsor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("requester_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("estimated_budget", sa.Numeric(18, 2), nullable=True),
            sa.Column("currency", sa.String(12), nullable=False, server_default="USD"),
            sa.Column("value_score", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("urgency_score", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("feasibility_score", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("risk_score", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("weighted_score", sa.Numeric(6, 2), nullable=False, server_default="3.00"),
            sa.Column("status", sa.String(24), nullable=False, server_default="submitted"),
            sa.Column("decision_rationale", sa.Text(), nullable=True),
            sa.Column("decided_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("converted_project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=True, unique=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("organization_id", "intake_code", name="uq_intake_org_code"),
        )
        op.create_index("ix_project_intakes_org", "project_intakes", ["organization_id"])

    # 5. Project Charters & Stage Gates (PM-04)
    if not _table_exists(insp, "project_charters"):
        op.create_table(
            "project_charters",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("objectives", sa.Text(), nullable=True),
            sa.Column("scope_in", sa.Text(), nullable=True),
            sa.Column("scope_out", sa.Text(), nullable=True),
            sa.Column("success_criteria", sa.Text(), nullable=True),
            sa.Column("cost_tolerance_pct", sa.Numeric(5, 2), nullable=False, server_default="10.00"),
            sa.Column("schedule_tolerance_days", sa.Integer(), nullable=False, server_default="14"),
            sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
            sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_project_charters_project", "project_charters", ["project_id"])

    if not _table_exists(insp, "project_gates"):
        op.create_table(
            "project_gates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("stage", sa.String(32), nullable=False),
            sa.Column("gate_state", sa.String(24), nullable=False, server_default="not_ready"),
            sa.Column("decision_note", sa.Text(), nullable=True),
            sa.Column("waiver_reason", sa.Text(), nullable=True),
            sa.Column("waiver_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("evidence_snapshot_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("submitted_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("decided_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("project_id", "stage", name="uq_project_gate_stage"),
        )
        op.create_index("ix_project_gates_project", "project_gates", ["project_id"])

    # 6. WBS Nodes (PM-06)
    if not _table_exists(insp, "project_wbs_nodes"):
        op.create_table(
            "project_wbs_nodes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("parent_id", sa.Integer(), sa.ForeignKey("project_wbs_nodes.id"), nullable=True),
            sa.Column("wbs_code", sa.String(32), nullable=False),
            sa.Column("title", sa.String(220), nullable=False),
            sa.Column("node_type", sa.String(24), nullable=False, server_default="work_package"),
            sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("budget_allocation", sa.Numeric(18, 2), nullable=False, server_default="0.00"),
            sa.Column("weight_pct", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("weight_pct >= 0 AND weight_pct <= 100", name="ck_wbs_weight_pct"),
        )
        op.create_index("ix_project_wbs_nodes_project", "project_wbs_nodes", ["project_id"])

    # 7. Project Tasks (create if missing, else add enterprise columns)
    if _table_exists(insp, "project_tasks"):
        for col_name, col_def in (
            ("wbs_node_id", sa.Column("wbs_node_id", sa.Integer(), sa.ForeignKey("project_wbs_nodes.id"), nullable=True)),
            ("parent_task_id", sa.Column("parent_task_id", sa.Integer(), sa.ForeignKey("project_tasks.id"), nullable=True)),
            ("assignee_user_id", sa.Column("assignee_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True)),
            ("start_date_typed", sa.Column("start_date_typed", sa.Date(), nullable=True)),
            ("due_date_typed", sa.Column("due_date_typed", sa.Date(), nullable=True)),
            ("planned_hours", sa.Column("planned_hours", sa.Numeric(10, 2), nullable=False, server_default="0.00")),
            ("actual_hours", sa.Column("actual_hours", sa.Numeric(10, 2), nullable=False, server_default="0.00")),
            ("remaining_hours", sa.Column("remaining_hours", sa.Numeric(10, 2), nullable=False, server_default="0.00")),
            ("is_milestone", sa.Column("is_milestone", sa.Boolean(), nullable=False, server_default="false")),
            ("version", sa.Column("version", sa.Integer(), nullable=False, server_default="1")),
        ):
            if not _col_exists(insp, "project_tasks", col_name):
                op.add_column("project_tasks", col_def)
    else:
        op.create_table(
            "project_tasks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("wbs_node_id", sa.Integer(), sa.ForeignKey("project_wbs_nodes.id"), nullable=True),
            sa.Column("parent_task_id", sa.Integer(), sa.ForeignKey("project_tasks.id"), nullable=True),
            sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contract_workflows.id"), nullable=True),
            sa.Column("title", sa.String(220), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("phase", sa.String(64), nullable=True, server_default="Execution"),
            sa.Column("assignee_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("assignee_name", sa.String(120), nullable=True),
            sa.Column("priority", sa.String(16), nullable=False, server_default="medium"),
            sa.Column("status", sa.String(24), nullable=False, server_default="todo"),
            sa.Column("start_date_typed", sa.Date(), nullable=True),
            sa.Column("due_date", sa.String(32), nullable=True),
            sa.Column("due_date_typed", sa.Date(), nullable=True),
            sa.Column("planned_hours", sa.Numeric(10, 2), nullable=False, server_default="0.00"),
            sa.Column("actual_hours", sa.Numeric(10, 2), nullable=False, server_default="0.00"),
            sa.Column("remaining_hours", sa.Numeric(10, 2), nullable=False, server_default="0.00"),
            sa.Column("is_milestone", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("progress_pct", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_project_tasks_project", "project_tasks", ["project_id"])

    # 8. Task Dependencies (PM-07)
    if not _table_exists(insp, "project_task_dependencies"):
        op.create_table(
            "project_task_dependencies",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("predecessor_task_id", sa.Integer(), sa.ForeignKey("project_tasks.id"), nullable=False),
            sa.Column("successor_task_id", sa.Integer(), sa.ForeignKey("project_tasks.id"), nullable=False),
            sa.Column("dependency_type", sa.String(4), nullable=False, server_default="FS"),
            sa.Column("lag_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("predecessor_task_id", "successor_task_id", name="uq_task_dep_pair"),
            sa.CheckConstraint("predecessor_task_id != successor_task_id", name="ck_task_dep_no_self"),
        )
        op.create_index("ix_project_task_deps_project", "project_task_dependencies", ["project_id"])

    # 9. Budget Lines & Cost Events (PM-15/16)
    if not _table_exists(insp, "project_budget_lines"):
        op.create_table(
            "project_budget_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("wbs_node_id", sa.Integer(), sa.ForeignKey("project_wbs_nodes.id"), nullable=True),
            sa.Column("category", sa.String(48), nullable=False, server_default="labor"),
            sa.Column("description", sa.String(240), nullable=False),
            sa.Column("planned_amount", sa.Numeric(18, 2), nullable=False, server_default="0.00"),
            sa.Column("currency", sa.String(12), nullable=False, server_default="USD"),
            sa.Column("baseline_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("planned_amount >= 0", name="ck_budget_line_nonneg"),
        )
        op.create_index("ix_project_budget_lines_project", "project_budget_lines", ["project_id"])

    if not _table_exists(insp, "project_cost_events"):
        op.create_table(
            "project_cost_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("wbs_node_id", sa.Integer(), sa.ForeignKey("project_wbs_nodes.id"), nullable=True),
            sa.Column("event_type", sa.String(24), nullable=False, server_default="actual"),
            sa.Column("category", sa.String(48), nullable=False, server_default="labor"),
            sa.Column("description", sa.String(240), nullable=False),
            sa.Column("amount", sa.Numeric(18, 2), nullable=False),
            sa.Column("currency", sa.String(12), nullable=False, server_default="USD"),
            sa.Column("source_ref", sa.String(120), nullable=True),
            sa.Column("status", sa.String(24), nullable=False, server_default="posted"),
            sa.Column("event_date", sa.Date(), nullable=True),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("organization_id", "project_id", "source_ref", name="uq_cost_event_source_ref"),
        )
        op.create_index("ix_project_cost_events_project", "project_cost_events", ["project_id"])

    # 10. Resource Allocations & Time Entries (PM-12/13)
    if not _table_exists(insp, "project_resource_allocations"):
        op.create_table(
            "project_resource_allocations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("resource_name", sa.String(160), nullable=False),
            sa.Column("role_title", sa.String(120), nullable=False, server_default="Contributor"),
            sa.Column("allocation_pct", sa.Integer(), nullable=False, server_default="50"),
            sa.Column("planned_hours", sa.Numeric(10, 2), nullable=False, server_default="0.00"),
            sa.Column("hourly_cost_rate", sa.Numeric(12, 2), nullable=True),
            sa.Column("currency", sa.String(12), nullable=False, server_default="USD"),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("status", sa.String(24), nullable=False, server_default="confirmed"),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("allocation_pct >= 1 AND allocation_pct <= 200", name="ck_alloc_pct_range"),
        )
        op.create_index("ix_project_res_alloc_project", "project_resource_allocations", ["project_id"])

    if not _table_exists(insp, "project_time_entries"):
        op.create_table(
            "project_time_entries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("task_id", sa.Integer(), sa.ForeignKey("project_tasks.id"), nullable=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("work_date", sa.Date(), nullable=False),
            sa.Column("hours", sa.Numeric(8, 2), nullable=False),
            sa.Column("billable", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("notes", sa.String(400), nullable=True),
            sa.Column("hourly_rate_snapshot", sa.Numeric(12, 2), nullable=True),
            sa.Column("cost_amount", sa.Numeric(18, 2), nullable=True),
            sa.Column("currency", sa.String(12), nullable=False, server_default="USD"),
            sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
            sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("posted_cost_event_id", sa.Integer(), sa.ForeignKey("project_cost_events.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("hours > 0 AND hours <= 24", name="ck_time_entry_hours"),
        )
        op.create_index("ix_project_time_entries_project", "project_time_entries", ["project_id"])

    # 11. RAID Risks (add enterprise columns if table exists)
    if _table_exists(insp, "project_risks"):
        for col_name, col_def in (
            ("item_type", sa.Column("item_type", sa.String(24), nullable=False, server_default="risk")),
            ("probability_score", sa.Column("probability_score", sa.Integer(), nullable=False, server_default="3")),
            ("impact_score", sa.Column("impact_score", sa.Integer(), nullable=False, server_default="3")),
            ("exposure_amount", sa.Column("exposure_amount", sa.Numeric(18, 2), nullable=True)),
            ("owner_user_id", sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True)),
            ("due_date_typed", sa.Column("due_date_typed", sa.Date(), nullable=True)),
            ("version", sa.Column("version", sa.Integer(), nullable=False, server_default="1")),
        ):
            if not _col_exists(insp, "project_risks", col_name):
                op.add_column("project_risks", col_def)
    else:
        op.create_table(
            "project_risks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contract_workflows.id"), nullable=True),
            sa.Column("item_type", sa.String(24), nullable=False, server_default="risk"),
            sa.Column("title", sa.String(220), nullable=False),
            sa.Column("category", sa.String(32), nullable=False, server_default="contractual"),
            sa.Column("severity", sa.String(16), nullable=False, server_default="medium"),
            sa.Column("likelihood", sa.String(16), nullable=False, server_default="medium"),
            sa.Column("probability_score", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("impact_score", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("exposure_amount", sa.Numeric(18, 2), nullable=True),
            sa.Column("mitigation_plan", sa.Text(), nullable=True),
            sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("owner_name", sa.String(120), nullable=True),
            sa.Column("due_date_typed", sa.Date(), nullable=True),
            sa.Column("status", sa.String(24), nullable=False, server_default="open"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_project_risks_project", "project_risks", ["project_id"])

    # 12. Integrated Change Requests (PM-20)
    if not _table_exists(insp, "project_change_requests"):
        op.create_table(
            "project_change_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("cr_number", sa.String(40), nullable=False),
            sa.Column("title", sa.String(220), nullable=False),
            sa.Column("change_type", sa.String(24), nullable=False, server_default="scope"),
            sa.Column("rationale", sa.Text(), nullable=True),
            sa.Column("cost_impact", sa.Numeric(18, 2), nullable=False, server_default="0.00"),
            sa.Column("schedule_impact_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(24), nullable=False, server_default="submitted"),
            sa.Column("decision_note", sa.Text(), nullable=True),
            sa.Column("requested_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("decided_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("project_id", "cr_number", name="uq_project_cr_number"),
        )
        op.create_index("ix_project_crs_project", "project_change_requests", ["project_id"])

    # 13. Project Memberships (PM-33)
    if not _table_exists(insp, "project_memberships"):
        op.create_table(
            "project_memberships",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("project_role", sa.String(32), nullable=False, server_default="member"),
            sa.Column("can_view_finance", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("granted_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("project_id", "user_id", name="uq_project_member_user"),
        )
        op.create_index("ix_project_memberships_project", "project_memberships", ["project_id"])


def downgrade():
    # Additive forward-safe migration; drop newly introduced tables in reverse dependency order
    for tbl in (
        "project_memberships",
        "project_change_requests",
        "project_time_entries",
        "project_resource_allocations",
        "project_cost_events",
        "project_budget_lines",
        "project_task_dependencies",
        "project_wbs_nodes",
        "project_gates",
        "project_charters",
        "project_intakes",
        "project_programmes",
        "project_portfolios",
    ):
        op.drop_table(tbl)
