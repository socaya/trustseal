"""Email verification: users.email_verified + email_verification_tokens.

Revision ID: i9a428c3e2f9
Revises: h8e206f1c0a7
"""
from alembic import op
import sqlalchemy as sa

revision = "i9a428c3e2f9"
down_revision = "h8e206f1c0a7"
branch_labels = None
depends_on = None


def upgrade():
    # Use IF NOT EXISTS so the migration remains idempotent when it
    # replays against a disposable schema built from the current
    # SQLAlchemy model via ``create_all`` — the model already declares
    # these columns, so a plain ``ADD COLUMN`` would raise
    # ``DuplicateColumn``.
    op.execute(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_password_change_at TIMESTAMP"
    )
    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("email", sa.String(120), nullable=False),
        sa.Column("token_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("issued_from_ip", sa.String(45), nullable=True),
    )
    op.create_index(
        "ix_email_verification_tokens_user_active",
        "email_verification_tokens",
        ["user_id"],
        postgresql_where=sa.text("consumed_at IS NULL"),
    )


def downgrade():
    op.drop_index(
        "ix_email_verification_tokens_user_active",
        table_name="email_verification_tokens",
    )
    op.drop_table("email_verification_tokens")
    op.drop_column("users", "last_password_change_at")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "email_verified")
