"""Enterprise Project Management Batch 3 schema (PM-23, PM-25, PM-28, PM-29, PM-31).

Revision ID: d4e5f6a7b806
Revises: c3d4e5f6a705
Create Date: 2026-11-27 05:55:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "d4e5f6a7b806"
down_revision = "c3d4e5f6a705"
branch_labels = None
depends_on = None


def _exists(insp, name: str) -> bool:
    return name in insp.get_table_names()


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not _exists(insp, "project_comments"):
        op.create_table(
            "project_comments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("parent_id", sa.Integer(), sa.ForeignKey("project_comments.id"), nullable=True),
            sa.Column("author_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("author_name", sa.String(140), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_project_comments_project", "project_comments", ["project_id"])

    if not _exists(insp, "project_approval_requests"):
        op.create_table(
            "project_approval_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("subject_type", sa.String(32), nullable=False, server_default="deliverable"),
            sa.Column("subject_title", sa.String(220), nullable=False),
            sa.Column("subject_hash", sa.String(64), nullable=False),
            sa.Column("approval_mode", sa.String(24), nullable=False, server_default="internal"),
            sa.Column("enforce_sod", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("requested_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("decided_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
            sa.Column("decision_note", sa.Text(), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_project_approvals_project", "project_approval_requests", ["project_id"])

    if not _exists(insp, "project_compliance_records"):
        op.create_table(
            "project_compliance_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("record_type", sa.String(24), nullable=False, server_default="permit"),
            sa.Column("title", sa.String(220), nullable=False),
            sa.Column("authority", sa.String(160), nullable=True),
            sa.Column("is_mandatory", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("is_restricted", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("expiry_date", sa.Date(), nullable=True),
            sa.Column("status", sa.String(24), nullable=False, server_default="active"),
            sa.Column("details", sa.Text(), nullable=True),
            sa.Column("reported_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_project_compliance_project", "project_compliance_records", ["project_id"])

    if not _exists(insp, "project_external_grants"):
        op.create_table(
            "project_external_grants",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("recipient_name", sa.String(160), nullable=False),
            sa.Column("recipient_email", sa.String(180), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("scope_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("granted_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_project_ext_grants_project", "project_external_grants", ["project_id"])

    if not _exists(insp, "project_templates"):
        op.create_table(
            "project_templates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("code", sa.String(40), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("category", sa.String(48), nullable=False, server_default="client_delivery"),
            sa.Column("delivery_methodology", sa.String(24), nullable=False, server_default="hybrid"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("default_wbs_json", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("default_gates_json", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_project_templates_org", "project_templates", ["organization_id"])


def downgrade():
    for tbl in (
        "project_templates",
        "project_external_grants",
        "project_compliance_records",
        "project_approval_requests",
        "project_comments",
    ):
        op.drop_table(tbl)
