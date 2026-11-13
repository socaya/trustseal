"""Add unique fencing identity for each outbox claim.

Revision ID: a6b7d820e3f1
Revises: f9b135a0c642
"""
from alembic import op
import sqlalchemy as sa

revision = "a6b7d820e3f1"
down_revision = "f9b135a0c642"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("outbox_events", sa.Column("lease_token", sa.String(36)))
    op.create_index("ix_outbox_events_lease_token", "outbox_events", ["lease_token"])


def downgrade():
    op.drop_index("ix_outbox_events_lease_token", table_name="outbox_events")
    op.drop_column("outbox_events", "lease_token")
