"""Per-participant conditional routing rules.

Revision ID: x4d973b8e7e4
Revises: w3c862f7d6d3
"""
from alembic import op
import sqlalchemy as sa

revision = "x4d973b8e7e4"
down_revision = "w3c862f7d6d3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "envelope_routing_rules",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "envelope_id",
            sa.Integer(),
            sa.ForeignKey("signing_envelopes.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "participant_id",
            sa.Integer(),
            sa.ForeignKey("envelope_participants.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("predicate", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_table("envelope_routing_rules")
