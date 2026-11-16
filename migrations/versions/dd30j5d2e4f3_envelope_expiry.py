"""Optional envelope expiry.

Revision ID: dd30j5d2e4f3
Revises: cc29i4c1d3e2
"""
from alembic import op
import sqlalchemy as sa

revision = "dd30j5d2e4f3"
down_revision = "cc29i4c1d3e2"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE signing_envelopes "
        "ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP"
    )


def downgrade():
    op.drop_column("signing_envelopes", "expires_at")
