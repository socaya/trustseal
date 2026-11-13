"""Append-only visible-stamped PDF derivatives.

Revision ID: m7b195f0c8e6
Revises: l6a084e9b7d5
"""
from alembic import op
import sqlalchemy as sa

revision = "m7b195f0c8e6"
down_revision = "l6a084e9b7d5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stamped_pdfs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("stamp_attestation_id", sa.BigInteger(), sa.ForeignKey("stamp_attestations.id"), nullable=False, unique=True),
        sa.Column("source_finalized_pdf_id", sa.BigInteger(), sa.ForeignKey("finalized_pdfs.id"), nullable=False),
        sa.Column("source_finalized_sha256", sa.String(64), nullable=False),
        sa.Column("original_document_sha256", sa.String(64), nullable=False),
        sa.Column("stamp_evidence_sha256", sa.String(64), nullable=False),
        sa.Column("signed_evidence_sha256", sa.String(64), nullable=False),
        sa.Column("object_key", sa.String(96), nullable=False, unique=True),
        sa.Column("output_sha256", sa.String(64), nullable=False),
        sa.Column("output_size", sa.BigInteger(), nullable=False),
        sa.Column("certificate_sha256", sa.String(64), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("x_pt", sa.Integer(), nullable=False),
        sa.Column("y_pt", sa.Integer(), nullable=False),
        sa.Column("issued_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("output_size > 0", name="ck_stamped_pdf_output_size"),
        sa.CheckConstraint("page_number >= 1", name="ck_stamped_pdf_page"),
        sa.CheckConstraint("x_pt >= 0 AND y_pt >= 0", name="ck_stamped_pdf_position"),
    )
    op.create_index("ix_stamped_pdfs_organization_id", "stamped_pdfs", ["organization_id"])
    op.execute("""
        CREATE TRIGGER trg_stamped_pdfs_append_only
        BEFORE UPDATE OR DELETE ON stamped_pdfs
        FOR EACH ROW EXECUTE FUNCTION trustseal_reject_snapshot_mutation()
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_stamped_pdfs_append_only ON stamped_pdfs")
    op.drop_index("ix_stamped_pdfs_organization_id", table_name="stamped_pdfs")
    op.drop_table("stamped_pdfs")
