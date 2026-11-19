"""tsd_stamp_revisions — immutable snapshots of published designs (§15)

Each row records the layout + SVG + design metadata at the moment of
publication. Lets the Studio restore earlier versions, lets audit
trails see exactly what a published stamp looked like, and lets
inserted receipts verify against the snapshot the user actually
published (not any later edit).

Revision ID: a1b2c3d4e602
Revises: a1b2c3d4e601
Create Date: 2026-11-19 00:15:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e602"
down_revision = "a1b2c3d4e601"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tsd_stamp_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stamp_id", sa.Integer(),
                  sa.ForeignKey("tsd_stamps.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("created_by_id", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status_at_snapshot", sa.String(length=16), nullable=False),
        sa.Column("layout", sa.JSON(), nullable=False),
        sa.Column("svg", sa.Text(), nullable=False),
        sa.Column("name_at_snapshot", sa.String(length=120), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("stamp_id", "version",
                            name="uq_stamp_revision_version"),
    )
    op.create_index("ix_tsd_stamp_revisions_stamp",
                    "tsd_stamp_revisions", ["stamp_id"])


def downgrade():
    op.drop_index("ix_tsd_stamp_revisions_stamp",
                  table_name="tsd_stamp_revisions")
    op.drop_table("tsd_stamp_revisions")
