"""Add MFA credentials and one-shot recovery codes.

Revision ID: y9b317a2c0e8
Revises: x8a206f1b9d7
"""
from alembic import op
import sqlalchemy as sa

revision = "y9b317a2c0e8"
down_revision = "x8a206f1b9d7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mfa_credentials",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False, start=1, cycle=False),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("secret_cipher", sa.String(512), nullable=False),
        sa.Column("activated_at", sa.DateTime()),
        sa.Column("disabled_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime()),
        sa.Column("last_counter", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "mfa_recovery_codes",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False, start=1, cycle=False),
            primary_key=True,
        ),
        sa.Column(
            "credential_id",
            sa.BigInteger(),
            sa.ForeignKey("mfa_credentials.id"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime()),
    )
    op.create_index(
        "ix_mfa_recovery_codes_credential_id",
        "mfa_recovery_codes",
        ["credential_id"],
    )


def downgrade():
    op.drop_index(
        "ix_mfa_recovery_codes_credential_id", table_name="mfa_recovery_codes"
    )
    op.drop_table("mfa_recovery_codes")
    op.drop_table("mfa_credentials")
