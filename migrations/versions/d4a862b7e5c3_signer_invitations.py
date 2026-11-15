"""Hashed, single-use signer invitations.

Revision ID: d4a862b7e5c3
Revises: c3f751e6d4b2
"""
from alembic import op
import sqlalchemy as sa

revision = "d4a862b7e5c3"
down_revision = "c3f751e6d4b2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "signer_invitations",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False, start=1, cycle=False),
            primary_key=True,
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
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "issued_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime()),
        sa.Column("revoked_at", sa.DateTime()),
        sa.Column("revoke_reason", sa.String(80)),
        sa.UniqueConstraint(
            "envelope_id", "participant_id", name="uq_signer_invitation_participant"
        ),
    )
    op.create_index(
        "ix_signer_invitations_envelope_id",
        "signer_invitations",
        ["envelope_id"],
    )


def downgrade():
    op.drop_index(
        "ix_signer_invitations_envelope_id", table_name="signer_invitations"
    )
    op.drop_table("signer_invitations")
