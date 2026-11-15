"""Refresh-token families and per-token lineage tracking.

Revision ID: z0c428b3d1f9
Revises: y9b317a2c0e8
"""
from alembic import op
import sqlalchemy as sa

revision = "z0c428b3d1f9"
down_revision = "y9b317a2c0e8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "refresh_token_families",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False, start=1, cycle=False),
            primary_key=True,
        ),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime()),
        sa.Column("revoke_reason", sa.String(80)),
    )
    op.create_index(
        "ix_refresh_token_families_user_id",
        "refresh_token_families",
        ["user_id"],
    )

    op.create_table(
        "refresh_token_jtis",
        sa.Column("jti", sa.String(64), primary_key=True),
        sa.Column(
            "family_id",
            sa.BigInteger(),
            sa.ForeignKey("refresh_token_families.id"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("rotated_at", sa.DateTime()),
        sa.Column("revoked_at", sa.DateTime()),
    )
    op.create_index(
        "ix_refresh_token_jtis_family_id", "refresh_token_jtis", ["family_id"]
    )
    op.create_index(
        "ix_refresh_token_jtis_user_id", "refresh_token_jtis", ["user_id"]
    )


def downgrade():
    op.drop_index("ix_refresh_token_jtis_user_id", table_name="refresh_token_jtis")
    op.drop_index("ix_refresh_token_jtis_family_id", table_name="refresh_token_jtis")
    op.drop_table("refresh_token_jtis")
    op.drop_index(
        "ix_refresh_token_families_user_id", table_name="refresh_token_families"
    )
    op.drop_table("refresh_token_families")
