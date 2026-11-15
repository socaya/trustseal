"""Add idempotency records for trust-critical client mutations.

Revision ID: w7f195e0a8c6
Revises: v6e084c9f7b5
"""
from alembic import op
import sqlalchemy as sa

revision = "w7f195e0a8c6"
down_revision = "v6e084c9f7b5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "idempotency_records",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False, start=1, cycle=False),
            primary_key=True,
        ),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.String(160), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer()),
        sa.Column("response_body", sa.JSON()),
        sa.Column("response_headers", sa.JSON()),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("locked_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "endpoint", "key", name="uq_idempotency_tenant_endpoint_key"
        ),
        sa.CheckConstraint(
            "state IN ('locked','completed','failed')", name="ck_idempotency_state"
        ),
    )
    op.create_index(
        "ix_idempotency_records_tenant_id", "idempotency_records", ["tenant_id"]
    )
    op.create_index(
        "ix_idempotency_records_expires_at", "idempotency_records", ["expires_at"]
    )


def downgrade():
    op.drop_index("ix_idempotency_records_expires_at", table_name="idempotency_records")
    op.drop_index("ix_idempotency_records_tenant_id", table_name="idempotency_records")
    op.drop_table("idempotency_records")
