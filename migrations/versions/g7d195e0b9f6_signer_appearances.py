"""Optional drawn signature appearances captured on /sign.

Revision ID: g7d195e0b9f6
Revises: f6c084d9a8e5
"""
from alembic import op
import sqlalchemy as sa

revision = "g7d195e0b9f6"
down_revision = "f6c084d9a8e5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "signer_appearances",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False, start=1, cycle=False),
            primary_key=True,
        ),
        sa.Column(
            "decision_id",
            sa.BigInteger(),
            sa.ForeignKey("signer_decisions.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "envelope_id",
            sa.Integer(),
            sa.ForeignKey("signing_envelopes.id"),
            nullable=False,
        ),
        sa.Column(
            "participant_id",
            sa.Integer(),
            sa.ForeignKey("envelope_participants.id"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(96), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("size_bytes > 0", name="ck_signer_appearance_size"),
        sa.CheckConstraint(
            "size_bytes <= 262144", name="ck_signer_appearance_size_cap"
        ),
    )


def downgrade():
    op.drop_table("signer_appearances")
