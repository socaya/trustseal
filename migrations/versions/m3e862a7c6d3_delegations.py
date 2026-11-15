"""Time-bound authority delegation.

Revision ID: m3e862a7c6d3
Revises: l2d751f6b5c2
"""
from alembic import op
import sqlalchemy as sa

revision = "m3e862a7c6d3"
down_revision = "l2d751f6b5c2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "delegations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "delegator_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "delegate_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("scope", sa.String(80), nullable=False),
        sa.Column("resource_type", sa.String(60), nullable=True),
        sa.Column("resource_id", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.Column(
            "granted_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column(
            "revoked_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("revoke_reason", sa.String(255), nullable=True),
        sa.CheckConstraint(
            "expires_at > starts_at", name="ck_delegations_window"
        ),
    )


def downgrade():
    op.drop_table("delegations")
