"""Immutable detached signer-review attestations.

Revision ID: g1a42e05fd90
Revises: f2a91d6e4b80
"""
from alembic import op
import sqlalchemy as sa

revision = "g1a42e05fd90"
down_revision = "f2a91d6e4b80"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "review_receipts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("decision_id", sa.BigInteger(), sa.ForeignKey("signer_decisions.id"), nullable=False, unique=True),
        sa.Column("envelope_id", sa.Integer(), sa.ForeignKey("signing_envelopes.id"), nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("algorithm", sa.String(16), nullable=False),
        sa.Column("key_id", sa.String(80), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_review_receipts_envelope_id", "review_receipts", ["envelope_id"])
    op.create_index("ix_review_receipts_organization_id", "review_receipts", ["organization_id"])
    op.execute("""
        CREATE TRIGGER trg_review_receipts_append_only
        BEFORE UPDATE OR DELETE ON review_receipts
        FOR EACH ROW EXECUTE FUNCTION trustseal_reject_snapshot_mutation()
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_review_receipts_append_only ON review_receipts")
    op.drop_index("ix_review_receipts_organization_id", table_name="review_receipts")
    op.drop_index("ix_review_receipts_envelope_id", table_name="review_receipts")
    op.drop_table("review_receipts")
