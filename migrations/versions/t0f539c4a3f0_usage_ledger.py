"""Deduplicated usage ledger.

Revision ID: t0f539c4a3f0
Revises: s9e428a3d2e9
"""
from alembic import op
import sqlalchemy as sa

revision = "t0f539c4a3f0"
down_revision = "s9e428a3d2e9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "usage_ledger_entries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("meter", sa.String(60), nullable=False),
        sa.Column("source_event_id", sa.String(120), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False, index=True),
        sa.Column(
            "actor_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "organization_id", "meter", "source_event_id",
            name="uq_usage_ledger_dedupe",
        ),
        sa.CheckConstraint("hits > 0", name="ck_usage_ledger_hits"),
    )


def downgrade():
    op.drop_table("usage_ledger_entries")
