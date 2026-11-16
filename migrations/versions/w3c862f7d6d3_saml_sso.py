"""SAML 2.0 SSO: provider configuration + assertion replay store.

Revision ID: w3c862f7d6d3
Revises: v2b751e6c5c2
"""
from alembic import op
import sqlalchemy as sa

revision = "w3c862f7d6d3"
down_revision = "v2b751e6c5c2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "saml_providers",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("entity_id", sa.String(255), nullable=False),
        sa.Column("sso_url", sa.String(500), nullable=False),
        sa.Column("x509_cert_pem", sa.Text(), nullable=False),
        sa.Column("audience", sa.String(255), nullable=False),
        sa.Column("attribute_mapping", sa.JSON(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "organization_id", "entity_id", name="uq_saml_provider_entity"
        ),
    )
    op.create_table(
        "saml_consumed_assertions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "provider_id",
            sa.Integer(),
            sa.ForeignKey("saml_providers.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("assertion_id", sa.String(255), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=False),
        sa.Column("not_on_or_after", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "provider_id", "assertion_id",
            name="uq_saml_consumed_assertion",
        ),
    )


def downgrade():
    op.drop_table("saml_consumed_assertions")
    op.drop_table("saml_providers")
