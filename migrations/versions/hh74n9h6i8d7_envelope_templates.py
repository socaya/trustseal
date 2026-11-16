"""Envelope templates (Phase S1).

Revision ID: hh74n9h6i8d7
Revises: gg63m8g5h7c6
"""
from alembic import op
import sqlalchemy as sa

revision = "hh74n9h6i8d7"
down_revision = "gg63m8g5h7c6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "envelope_templates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer,
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(400), nullable=True),
        sa.Column(
            "routing_mode",
            sa.String(20),
            nullable=False,
            server_default="sequential",
        ),
        sa.Column("quorum_required", sa.Integer, nullable=True),
        sa.Column("reminder_cooloff_hours", sa.Integer, nullable=True),
        sa.Column("reminder_max_count", sa.Integer, nullable=True),
        sa.Column("expires_in_hours", sa.Integer, nullable=True),
        sa.Column(
            "created_by_id",
            sa.Integer,
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "organization_id", "name", name="uq_envelope_template_org_name"
        ),
        sa.CheckConstraint(
            "routing_mode IN ('sequential','parallel','quorum')",
            name="ck_envelope_template_routing_mode",
        ),
        sa.CheckConstraint(
            "(routing_mode = 'quorum' AND quorum_required IS NOT NULL AND quorum_required > 0) "
            "OR (routing_mode <> 'quorum' AND quorum_required IS NULL)",
            name="ck_envelope_template_quorum_required",
        ),
        sa.CheckConstraint(
            "reminder_cooloff_hours IS NULL OR reminder_cooloff_hours BETWEEN 1 AND 720",
            name="ck_envelope_template_reminder_cooloff_range",
        ),
        sa.CheckConstraint(
            "reminder_max_count IS NULL OR reminder_max_count BETWEEN 1 AND 50",
            name="ck_envelope_template_reminder_max_count_range",
        ),
        sa.CheckConstraint(
            "expires_in_hours IS NULL OR expires_in_hours BETWEEN 1 AND 8760",
            name="ck_envelope_template_expires_in_hours_range",
        ),
        sa.CheckConstraint(
            "char_length(name) >= 1",
            name="ck_envelope_template_name_present",
        ),
    )
    op.create_index(
        "ix_envelope_templates_organization_id",
        "envelope_templates",
        ["organization_id"],
    )
    op.create_table(
        "envelope_template_participants",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "template_id",
            sa.Integer,
            sa.ForeignKey("envelope_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("signing_order", sa.Integer, nullable=False),
        sa.Column(
            "role",
            sa.String(20),
            nullable=False,
            server_default="signer",
        ),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "template_id", "user_id", name="uq_envelope_template_user"
        ),
        sa.UniqueConstraint(
            "template_id",
            "signing_order",
            name="uq_envelope_template_order",
        ),
        sa.CheckConstraint(
            "signing_order > 0", name="ck_envelope_template_order"
        ),
        sa.CheckConstraint(
            "role IN ('signer','witness')",
            name="ck_envelope_template_role",
        ),
    )
    op.create_index(
        "ix_envelope_template_participants_template_id",
        "envelope_template_participants",
        ["template_id"],
    )
    # RLS matches the shared pattern via ``trustseal_tenant_match``.
    bind = op.get_bind()
    bind.exec_driver_sql(
        "ALTER TABLE envelope_templates ENABLE ROW LEVEL SECURITY"
    )
    bind.exec_driver_sql(
        "DROP POLICY IF EXISTS trustseal_tenant_isolation ON envelope_templates"
    )
    bind.exec_driver_sql(
        "CREATE POLICY trustseal_tenant_isolation ON envelope_templates "
        "USING (trustseal_tenant_match(organization_id)) "
        "WITH CHECK (trustseal_tenant_match(organization_id))"
    )
    # Template participants are scoped indirectly via a subquery.
    bind.exec_driver_sql(
        "ALTER TABLE envelope_template_participants ENABLE ROW LEVEL SECURITY"
    )
    bind.exec_driver_sql(
        "DROP POLICY IF EXISTS trustseal_tenant_isolation ON envelope_template_participants"
    )
    bind.exec_driver_sql(
        "CREATE POLICY trustseal_tenant_isolation ON envelope_template_participants "
        "USING (template_id IN ("
        "  SELECT id FROM envelope_templates WHERE trustseal_tenant_match(organization_id)"
        ")) "
        "WITH CHECK (template_id IN ("
        "  SELECT id FROM envelope_templates WHERE trustseal_tenant_match(organization_id)"
        "))"
    )


def downgrade():
    bind = op.get_bind()
    bind.exec_driver_sql(
        "DROP POLICY IF EXISTS trustseal_tenant_isolation ON envelope_template_participants"
    )
    bind.exec_driver_sql(
        "ALTER TABLE envelope_template_participants DISABLE ROW LEVEL SECURITY"
    )
    bind.exec_driver_sql(
        "DROP POLICY IF EXISTS trustseal_tenant_isolation ON envelope_templates"
    )
    bind.exec_driver_sql(
        "ALTER TABLE envelope_templates DISABLE ROW LEVEL SECURITY"
    )
    op.drop_index(
        "ix_envelope_template_participants_template_id",
        table_name="envelope_template_participants",
    )
    op.drop_table("envelope_template_participants")
    op.drop_index(
        "ix_envelope_templates_organization_id",
        table_name="envelope_templates",
    )
    op.drop_table("envelope_templates")
