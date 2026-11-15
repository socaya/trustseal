"""SCIM 2.0 service-account tokens.

Revision ID: b2e640d5f3a1
Revises: a1d539c4e2f0
"""
from alembic import op
import sqlalchemy as sa

revision = "b2e640d5f3a1"
down_revision = "a1d539c4e2f0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "scim_service_accounts",
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
            nullable=False,
        ),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime()),
    )
    op.create_index(
        "ix_scim_service_accounts_organization_id",
        "scim_service_accounts",
        ["organization_id"],
    )


def downgrade():
    op.drop_index(
        "ix_scim_service_accounts_organization_id",
        table_name="scim_service_accounts",
    )
    op.drop_table("scim_service_accounts")
