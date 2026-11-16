"""Operator notifications (Phase W1).

Revision ID: jj96p1j8k0f9
Revises: ii85o0i7j9e8
"""
from alembic import op
import sqlalchemy as sa

revision = "jj96p1j8k0f9"
down_revision = "ii85o0i7j9e8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "operator_notifications",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer,
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "recipient_user_id",
            sa.Integer,
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(60), nullable=False),
        sa.Column("subject_type", sa.String(60), nullable=False),
        sa.Column("subject_id", sa.BigInteger, nullable=True),
        sa.Column("summary", sa.String(400), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("read_at", sa.DateTime, nullable=True),
        sa.CheckConstraint(
            "char_length(kind) >= 1",
            name="ck_operator_notification_kind_present",
        ),
        sa.CheckConstraint(
            "char_length(summary) >= 1",
            name="ck_operator_notification_summary_present",
        ),
    )
    op.create_index(
        "ix_operator_notifications_organization_id",
        "operator_notifications",
        ["organization_id"],
    )
    op.create_index(
        "ix_operator_notifications_recipient_user_id",
        "operator_notifications",
        ["recipient_user_id"],
    )
    op.create_index(
        "ix_operator_notifications_kind",
        "operator_notifications",
        ["kind"],
    )
    op.create_index(
        "ix_operator_notifications_created_at",
        "operator_notifications",
        ["created_at"],
    )
    op.create_index(
        "ix_operator_notifications_recipient_unread",
        "operator_notifications",
        ["recipient_user_id", "read_at"],
    )
    bind = op.get_bind()
    bind.exec_driver_sql(
        "ALTER TABLE operator_notifications ENABLE ROW LEVEL SECURITY"
    )
    bind.exec_driver_sql(
        "DROP POLICY IF EXISTS trustseal_tenant_isolation ON operator_notifications"
    )
    bind.exec_driver_sql(
        "CREATE POLICY trustseal_tenant_isolation ON operator_notifications "
        "USING (trustseal_tenant_match(organization_id)) "
        "WITH CHECK (trustseal_tenant_match(organization_id))"
    )


def downgrade():
    bind = op.get_bind()
    bind.exec_driver_sql(
        "DROP POLICY IF EXISTS trustseal_tenant_isolation ON operator_notifications"
    )
    bind.exec_driver_sql(
        "ALTER TABLE operator_notifications DISABLE ROW LEVEL SECURITY"
    )
    for name in (
        "ix_operator_notifications_recipient_unread",
        "ix_operator_notifications_created_at",
        "ix_operator_notifications_kind",
        "ix_operator_notifications_recipient_user_id",
        "ix_operator_notifications_organization_id",
    ):
        op.drop_index(name, table_name="operator_notifications")
    op.drop_table("operator_notifications")
