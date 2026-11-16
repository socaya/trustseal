"""Reminder-scanner bookkeeping on signer_invitations.

Revision ID: ee41k6e3f5a4
Revises: dd30j5d2e4f3
"""
from alembic import op
import sqlalchemy as sa

revision = "ee41k6e3f5a4"
down_revision = "dd30j5d2e4f3"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE signer_invitations "
        "ADD COLUMN IF NOT EXISTS last_reminder_at TIMESTAMP"
    )


def downgrade():
    op.drop_column("signer_invitations", "last_reminder_at")
