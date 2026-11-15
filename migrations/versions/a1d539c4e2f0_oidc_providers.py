"""Tenant-scoped OIDC provider configuration.

Revision ID: a1d539c4e2f0
Revises: z0c428b3d1f9
"""
from alembic import op
import sqlalchemy as sa

revision = "a1d539c4e2f0"
down_revision = "z0c428b3d1f9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "oidc_providers",
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
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("issuer", sa.String(256), nullable=False),
        sa.Column("client_id", sa.String(256), nullable=False),
        sa.Column("client_secret_cipher", sa.String(1024), nullable=False),
        sa.Column("trusted_email_domains", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "organization_id", "slug", name="uq_oidc_provider_slug"
        ),
    )
    op.create_index(
        "ix_oidc_providers_organization_id", "oidc_providers", ["organization_id"]
    )


def downgrade():
    op.drop_index(
        "ix_oidc_providers_organization_id", table_name="oidc_providers"
    )
    op.drop_table("oidc_providers")
