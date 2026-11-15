"""Signed anchors over the audit-event chain tip.

Revision ID: e5b973c8f7d4
Revises: d4a862b7e5c3
"""
from alembic import op
import sqlalchemy as sa

revision = "e5b973c8f7d4"
down_revision = "d4a862b7e5c3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "audit_chain_anchors",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False, start=1, cycle=False),
            primary_key=True,
        ),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id"),
        ),
        sa.Column("anchor_event_id", sa.BigInteger()),
        sa.Column("chain_tip_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("algorithm", sa.String(16), nullable=False),
        sa.Column("key_id", sa.String(80), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column(
            "operator_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_audit_chain_anchors_organization_id",
        "audit_chain_anchors",
        ["organization_id"],
    )


def downgrade():
    op.drop_index(
        "ix_audit_chain_anchors_organization_id",
        table_name="audit_chain_anchors",
    )
    op.drop_table("audit_chain_anchors")
