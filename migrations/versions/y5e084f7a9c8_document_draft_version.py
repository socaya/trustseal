"""Optimistic concurrency token on document_drafts.

Revision ID: y5e084f7a9c8
Revises: x4d973b8e7e4
"""
from alembic import op
import sqlalchemy as sa

revision = "y5e084f7a9c8"
down_revision = "x4d973b8e7e4"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE document_drafts "
        "ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1"
    )


def downgrade():
    op.drop_column("document_drafts", "version")
