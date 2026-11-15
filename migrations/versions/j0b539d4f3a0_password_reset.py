"""Password reset tokens.

Revision ID: j0b539d4f3a0
Revises: i9a428c3e2f9
"""
from alembic import op
import sqlalchemy as sa

revision = "j0b539d4f3a0"
down_revision = "i9a428c3e2f9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("token_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("issued_from_ip", sa.String(45), nullable=True),
    )
    op.create_index(
        "ix_password_reset_tokens_user_active",
        "password_reset_tokens",
        ["user_id"],
        postgresql_where=sa.text("consumed_at IS NULL"),
    )


def downgrade():
    op.drop_index(
        "ix_password_reset_tokens_user_active",
        table_name="password_reset_tokens",
    )
    op.drop_table("password_reset_tokens")
