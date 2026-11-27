"""Enterprise Timesheets v2.1 schema (PM-13.01..PM-13.16).

Revision ID: e5f6a7b8c907
Revises: d4e5f6a7b806
Create Date: 2026-11-27 06:22:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e5f6a7b8c907"
down_revision = "d4e5f6a7b806"
branch_labels = None
depends_on = None


def _table_exists(insp, name: str) -> bool:
    return name in insp.get_table_names()


def _col_exists(insp, table: str, col: str) -> bool:
    if not _table_exists(insp, table):
        return False
    return any(c["name"] == col for c in insp.get_columns(table))


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if _table_exists(insp, "project_time_entries"):
        for cname, cdef in (
            ("wbs_node_id", sa.Column("wbs_node_id", sa.Integer(), sa.ForeignKey("project_wbs_nodes.id"), nullable=True)),
            ("contract_id", sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contract_workflows.id"), nullable=True)),
            ("duration_minutes", sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="0")),
            ("cost_code", sa.Column("cost_code", sa.String(48), nullable=True)),
            ("return_reason", sa.Column("return_reason", sa.String(400), nullable=True)),
            ("billing_rate_snapshot", sa.Column("billing_rate_snapshot", sa.Numeric(12, 2), nullable=True)),
            ("billable_amount", sa.Column("billable_amount", sa.Numeric(18, 2), nullable=True)),
            ("locked_at", sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True)),
        ):
            if not _col_exists(insp, "project_time_entries", cname):
                op.add_column("project_time_entries", cdef)

    if not _table_exists(insp, "project_time_adjustments"):
        op.create_table(
            "project_time_adjustments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("original_entry_id", sa.Integer(), sa.ForeignKey("project_time_entries.id"), nullable=False),
            sa.Column("delta_hours", sa.Numeric(8, 2), nullable=False),
            sa.Column("delta_cost_amount", sa.Numeric(18, 2), nullable=False, server_default="0.00"),
            sa.Column("reason", sa.String(400), nullable=False),
            sa.Column("posted_cost_event_id", sa.Integer(), sa.ForeignKey("project_cost_events.id"), nullable=True),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_project_time_adj_orig", "project_time_adjustments", ["original_entry_id"])


def downgrade():
    op.drop_table("project_time_adjustments")
