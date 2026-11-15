"""User session / device tracking.

Revision ID: k1c640e5a4b1
Revises: j0b539d4f3a0
"""
from alembic import op
import sqlalchemy as sa

revision = "k1c640e5a4b1"
down_revision = "j0b539d4f3a0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "family_id",
            sa.BigInteger(),
            sa.ForeignKey("refresh_token_families.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("device_label", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoke_reason", sa.String(60), nullable=True),
    )
    op.create_index(
        "ix_user_sessions_active",
        "user_sessions",
        ["user_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade():
    op.drop_index("ix_user_sessions_active", table_name="user_sessions")
    op.drop_table("user_sessions")
