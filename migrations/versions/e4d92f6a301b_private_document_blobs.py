"""Private scanned PDF manifest with append-only enforcement.

Revision ID: e4d92f6a301b
Revises: d0a7bc120e34
"""
from alembic import op
import sqlalchemy as sa

revision = "e4d92f6a301b"
down_revision = "d0a7bc120e34"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_blobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(96), nullable=False, unique=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("scanner", sa.String(32), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("document_id", "revision", name="uq_document_blobs_revision"),
        sa.CheckConstraint("file_size > 0", name="ck_document_blobs_nonempty"),
    )
    op.create_index("ix_document_blobs_document_id", "document_blobs", ["document_id"])
    op.execute("""
        CREATE TRIGGER trg_document_blobs_append_only
        BEFORE UPDATE OR DELETE ON document_blobs
        FOR EACH ROW EXECUTE FUNCTION trustseal_reject_snapshot_mutation()
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_document_blobs_append_only ON document_blobs")
    op.drop_index("ix_document_blobs_document_id", table_name="document_blobs")
    op.drop_table("document_blobs")
