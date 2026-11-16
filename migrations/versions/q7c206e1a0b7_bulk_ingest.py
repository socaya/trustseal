"""Bulk ingest batches + items.

Revision ID: q7c206e1a0b7
Revises: p6b195d0f9a6
"""
from alembic import op
import sqlalchemy as sa

revision = "q7c206e1a0b7"
down_revision = "p6b195d0f9a6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bulk_ingest_batches",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
    )
    op.create_table(
        "bulk_ingest_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "batch_id",
            sa.BigInteger(),
            sa.ForeignKey("bulk_ingest_batches.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("documents.id"),
            nullable=True,
        ),
        sa.Column(
            "blob_id",
            sa.Integer(),
            sa.ForeignKey("document_blobs.id"),
            nullable=True,
        ),
        sa.Column("error_code", sa.String(60), nullable=True),
        sa.Column("error_message", sa.String(400), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','succeeded','failed')",
            name="ck_bulk_ingest_item_status",
        ),
    )


def downgrade():
    op.drop_table("bulk_ingest_items")
    op.drop_table("bulk_ingest_batches")
