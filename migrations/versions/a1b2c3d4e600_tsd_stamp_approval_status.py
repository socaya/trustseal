"""Approval workflow — status + published_at/by on tsd_stamps

Draft → Review → Published → (Archived). Published stamps are
immutable; edits must duplicate to a new draft. Spec §14.

Revision ID: a1b2c3d4e600
Revises: a1b2c3d4e5ff
Create Date: 2026-11-18 23:45:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e600"
down_revision = "a1b2c3d4e5ff"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tsd_stamps",
        sa.Column("status", sa.String(length=16), nullable=False,
                  server_default="draft"),
    )
    op.add_column(
        "tsd_stamps",
        sa.Column("published_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "tsd_stamps",
        sa.Column("published_by_id", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_check_constraint(
        "ck_tsd_stamp_status", "tsd_stamps",
        "status IN ('draft','review','published','archived')",
    )
    op.create_index("ix_tsd_stamps_status", "tsd_stamps", ["status"])


def downgrade():
    op.drop_index("ix_tsd_stamps_status", table_name="tsd_stamps")
    op.drop_constraint("ck_tsd_stamp_status", "tsd_stamps", type_="check")
    op.drop_column("tsd_stamps", "published_by_id")
    op.drop_column("tsd_stamps", "published_at")
    op.drop_column("tsd_stamps", "status")
