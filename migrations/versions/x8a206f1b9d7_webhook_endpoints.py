"""Add webhook endpoint and delivery tables.

Revision ID: x8a206f1b9d7
Revises: w7f195e0a8c6
"""
from alembic import op
import sqlalchemy as sa

revision = "x8a206f1b9d7"
down_revision = "w7f195e0a8c6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "webhook_endpoints",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False, start=1, cycle=False),
            primary_key=True,
        ),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("url", sa.String(512), nullable=False),
        sa.Column("secret_hash", sa.String(128), nullable=False),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("description", sa.String(200)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "organization_id", "url", name="uq_webhook_endpoint_org_url"
        ),
    )
    op.create_index(
        "ix_webhook_endpoints_organization_id",
        "webhook_endpoints",
        ["organization_id"],
    )

    op.create_table(
        "webhook_deliveries",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False, start=1, cycle=False),
            primary_key=True,
        ),
        sa.Column(
            "endpoint_id",
            sa.BigInteger(),
            sa.ForeignKey("webhook_endpoints.id"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(), nullable=False),
        sa.Column("response_status", sa.Integer()),
        sa.Column("response_excerpt", sa.String(400)),
        sa.Column("last_error", sa.String(400)),
        sa.Column("sent_at", sa.DateTime()),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "endpoint_id", "event_id", name="uq_webhook_delivery_endpoint_event"
        ),
        sa.CheckConstraint(
            "status IN ('pending','in_flight','succeeded','failed','dead')",
            name="ck_webhook_delivery_status",
        ),
        sa.CheckConstraint("retry_count >= 0", name="ck_webhook_delivery_retries"),
    )
    op.create_index(
        "ix_webhook_deliveries_endpoint_id", "webhook_deliveries", ["endpoint_id"]
    )
    op.create_index(
        "ix_webhook_deliveries_organization_id",
        "webhook_deliveries",
        ["organization_id"],
    )
    op.create_index(
        "ix_webhook_deliveries_pending",
        "webhook_deliveries",
        ["status", "next_retry_at"],
    )


def downgrade():
    op.drop_index("ix_webhook_deliveries_pending", table_name="webhook_deliveries")
    op.drop_index(
        "ix_webhook_deliveries_organization_id", table_name="webhook_deliveries"
    )
    op.drop_index("ix_webhook_deliveries_endpoint_id", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_index(
        "ix_webhook_endpoints_organization_id", table_name="webhook_endpoints"
    )
    op.drop_table("webhook_endpoints")
