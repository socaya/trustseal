"""SCIM service account lifecycle columns.

Revision ID: cc29i4c1d3e2
Revises: bb18h3b0c2d1
"""
from alembic import op
import sqlalchemy as sa

revision = "cc29i4c1d3e2"
down_revision = "bb18h3b0c2d1"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE scim_service_accounts "
        "ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP"
    )
    op.execute(
        "ALTER TABLE scim_service_accounts "
        "ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMP"
    )
    op.execute(
        "ALTER TABLE scim_service_accounts "
        "ADD COLUMN IF NOT EXISTS revoked_by_id INTEGER "
        "REFERENCES users(id)"
    )
    op.execute(
        "ALTER TABLE scim_service_accounts "
        "ADD COLUMN IF NOT EXISTS revoke_reason VARCHAR(200)"
    )
    op.execute(
        "ALTER TABLE scim_service_accounts "
        "ADD COLUMN IF NOT EXISTS rotated_from_id BIGINT"
    )
    op.execute(
        "ALTER TABLE scim_service_accounts "
        "DROP CONSTRAINT IF EXISTS fk_scim_rotated_from"
    )
    op.execute(
        "ALTER TABLE scim_service_accounts "
        "ADD CONSTRAINT fk_scim_rotated_from "
        "FOREIGN KEY (rotated_from_id) REFERENCES scim_service_accounts(id)"
    )


def downgrade():
    op.execute(
        "ALTER TABLE scim_service_accounts "
        "DROP CONSTRAINT IF EXISTS fk_scim_rotated_from"
    )
    op.drop_column("scim_service_accounts", "rotated_from_id")
    op.drop_column("scim_service_accounts", "revoke_reason")
    op.drop_column("scim_service_accounts", "revoked_by_id")
    op.drop_column("scim_service_accounts", "revoked_at")
    op.drop_column("scim_service_accounts", "expires_at")
