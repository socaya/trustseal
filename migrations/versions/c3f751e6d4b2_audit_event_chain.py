"""Chained-hash columns on security_events.

Each row records SHA-256(previous_event_hash || canonical_payload). A
``verify_chain(tenant_id)`` service recomputes the chain from scratch
and surfaces breaks — the sign that an event was reordered, inserted,
or deleted.

The chain is tenant-scoped: every tenant has its own sequence so one
tenant's audit stream cannot be used to forge another's.

Revision ID: c3f751e6d4b2
Revises: b2e640d5f3a1
"""
from alembic import op
import sqlalchemy as sa

revision = "c3f751e6d4b2"
down_revision = "b2e640d5f3a1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "security_events",
        sa.Column("prev_event_hash", sa.String(64)),
    )
    op.add_column(
        "security_events",
        sa.Column("event_hash", sa.String(64)),
    )
    op.create_index(
        "ix_security_events_tenant_chain",
        "security_events",
        ["organization_id", "id"],
    )


def downgrade():
    op.drop_index(
        "ix_security_events_tenant_chain", table_name="security_events"
    )
    op.drop_column("security_events", "event_hash")
    op.drop_column("security_events", "prev_event_hash")
