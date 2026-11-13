"""Create immutable draft text snapshots.

Revision ID: c6e8a2f74109
Revises: b3f1d4c7e901
"""
from alembic import op
import sqlalchemy as sa

revision = "c6e8a2f74109"
down_revision = "b3f1d4c7e901"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("canonical_content", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("document_id", "revision", name="uq_document_snapshots_revision"),
    )
    op.create_index("ix_document_snapshots_document_id", "document_snapshots", ["document_id"])


def downgrade():
    op.drop_index("ix_document_snapshots_document_id", table_name="document_snapshots")
    op.drop_table("document_snapshots")
