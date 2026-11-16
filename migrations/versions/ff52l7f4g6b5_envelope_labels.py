"""Envelope labels — operator-tagged signing envelopes (Phase Q1).

Revision ID: ff52l7f4g6b5
Revises: ee41k6e3f5a4
"""
from alembic import op
import sqlalchemy as sa

revision = "ff52l7f4g6b5"
down_revision = "ee41k6e3f5a4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "envelope_labels",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "envelope_id",
            sa.Integer,
            sa.ForeignKey("signing_envelopes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.Integer,
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("label", sa.String(60), nullable=False),
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
        sa.UniqueConstraint(
            "envelope_id", "label", name="uq_envelope_label"
        ),
        sa.CheckConstraint(
            "char_length(label) >= 1 AND char_length(label) <= 60",
            name="ck_envelope_label_length",
        ),
    )
    op.create_index(
        "ix_envelope_labels_envelope_id",
        "envelope_labels",
        ["envelope_id"],
    )
    op.create_index(
        "ix_envelope_labels_organization_id",
        "envelope_labels",
        ["organization_id"],
    )
    op.create_index(
        "ix_envelope_labels_org_label",
        "envelope_labels",
        ["organization_id", "label"],
    )
    # RLS: reuse the ``trustseal_tenant_match`` helper from migration
    # ``h8e206f1c0a7`` so the policy is identical to every other
    # tenant-scoped table.
    bind = op.get_bind()
    bind.exec_driver_sql(
        "ALTER TABLE envelope_labels ENABLE ROW LEVEL SECURITY"
    )
    bind.exec_driver_sql(
        "DROP POLICY IF EXISTS trustseal_tenant_isolation ON envelope_labels"
    )
    bind.exec_driver_sql(
        "CREATE POLICY trustseal_tenant_isolation ON envelope_labels "
        "USING (trustseal_tenant_match(organization_id)) "
        "WITH CHECK (trustseal_tenant_match(organization_id))"
    )


def downgrade():
    bind = op.get_bind()
    bind.exec_driver_sql(
        "DROP POLICY IF EXISTS trustseal_tenant_isolation ON envelope_labels"
    )
    bind.exec_driver_sql(
        "ALTER TABLE envelope_labels DISABLE ROW LEVEL SECURITY"
    )
    op.drop_index(
        "ix_envelope_labels_org_label", table_name="envelope_labels"
    )
    op.drop_index(
        "ix_envelope_labels_organization_id", table_name="envelope_labels"
    )
    op.drop_index(
        "ix_envelope_labels_envelope_id", table_name="envelope_labels"
    )
    op.drop_table("envelope_labels")
