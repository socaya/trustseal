"""Break-glass grants.

Revision ID: bb18h3b0c2d1
Revises: aa07g2a9b1c0
"""
from alembic import op
import sqlalchemy as sa

revision = "bb18h3b0c2d1"
down_revision = "aa07g2a9b1c0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "break_glass_grants",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "operator_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "granted_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id"),
            nullable=True,
        ),
        sa.Column("scope", sa.String(80), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column(
            "revoked_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("revoke_reason", sa.String(500), nullable=True),
    )


def downgrade():
    op.drop_table("break_glass_grants")
