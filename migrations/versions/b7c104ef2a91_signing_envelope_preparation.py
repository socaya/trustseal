"""Add preparatory signing envelopes and participant order.

Revision ID: b7c104ef2a91
Revises: a6b7d820e3f1
"""
from alembic import op
import sqlalchemy as sa

revision = "b7c104ef2a91"
down_revision = "a6b7d820e3f1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "signing_envelopes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("document_blob_id", sa.Integer(), sa.ForeignKey("document_blobs.id"), nullable=False),
        sa.Column("document_sha256", sa.String(64), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("prepared_at", sa.DateTime()),
        sa.Column("cancelled_at", sa.DateTime()),
        sa.CheckConstraint("state IN ('draft','prepared','cancelled')", name="ck_envelope_preparation_state"),
    )
    op.create_index("ix_signing_envelopes_organization_id", "signing_envelopes", ["organization_id"])
    op.create_index("ix_signing_envelopes_document_id", "signing_envelopes", ["document_id"])
    op.create_table(
        "envelope_participants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("envelope_id", sa.Integer(), sa.ForeignKey("signing_envelopes.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("signing_order", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("envelope_id", "user_id", name="uq_envelope_participant_user"),
        sa.UniqueConstraint("envelope_id", "signing_order", name="uq_envelope_participant_order"),
        sa.CheckConstraint("signing_order > 0", name="ck_envelope_participant_order"),
    )
    op.create_index("ix_envelope_participants_envelope_id", "envelope_participants", ["envelope_id"])


def downgrade():
    op.drop_index("ix_envelope_participants_envelope_id", table_name="envelope_participants")
    op.drop_table("envelope_participants")
    op.drop_index("ix_signing_envelopes_document_id", table_name="signing_envelopes")
    op.drop_index("ix_signing_envelopes_organization_id", table_name="signing_envelopes")
    op.drop_table("signing_envelopes")
