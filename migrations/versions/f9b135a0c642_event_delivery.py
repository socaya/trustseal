"""Create secure event and transactional outbox primitives.

Revision ID: f9b135a0c642
Revises: e4d92f6a301b
"""
from alembic import op
import sqlalchemy as sa

revision = "f9b135a0c642"
down_revision = "e4d92f6a301b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "security_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id")),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(60), nullable=False),
        sa.Column("resource_id", sa.Integer()),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_security_events_organization_id", "security_events", ["organization_id"])
    op.create_index("ix_security_events_actor_id", "security_events", ["actor_id"])
    op.execute("""CREATE TRIGGER trg_security_events_append_only
        BEFORE UPDATE OR DELETE ON security_events
        FOR EACH ROW EXECUTE FUNCTION trustseal_reject_snapshot_mutation()""")
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("aggregate_type", sa.String(60), nullable=False),
        sa.Column("aggregate_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id")),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("locked_until", sa.DateTime()),
        sa.Column("last_error", sa.String(200)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime()),
        sa.CheckConstraint("attempts >= 0", name="ck_outbox_attempts"),
        sa.CheckConstraint("state IN ('pending','processing','completed','dead')", name="ck_outbox_state"),
    )
    op.create_index("ix_outbox_events_organization_id", "outbox_events", ["organization_id"])
    op.create_index("ix_outbox_events_state", "outbox_events", ["state"])
    op.create_index("ix_outbox_claim", "outbox_events", ["state", "next_attempt_at", "locked_until"])


def downgrade():
    op.drop_index("ix_outbox_claim", table_name="outbox_events")
    op.drop_index("ix_outbox_events_state", table_name="outbox_events")
    op.drop_index("ix_outbox_events_organization_id", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.execute("DROP TRIGGER IF EXISTS trg_security_events_append_only ON security_events")
    op.drop_index("ix_security_events_actor_id", table_name="security_events")
    op.drop_index("ix_security_events_organization_id", table_name="security_events")
    op.drop_table("security_events")
