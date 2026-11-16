"""Document labels (Phase Y1).

Revision ID: kk07q2k9l1g0
Revises: jj96p1j8k0f9
"""
from alembic import op
import sqlalchemy as sa

revision = "kk07q2k9l1g0"
down_revision = "jj96p1j8k0f9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_labels",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "document_id",
            sa.Integer,
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
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
            "document_id", "label", name="uq_document_label"
        ),
        sa.CheckConstraint(
            "char_length(label) >= 1 AND char_length(label) <= 60",
            name="ck_document_label_length",
        ),
    )
    op.create_index(
        "ix_document_labels_document_id",
        "document_labels",
        ["document_id"],
    )
    op.create_index(
        "ix_document_labels_organization_id",
        "document_labels",
        ["organization_id"],
    )
    op.create_index(
        "ix_document_labels_org_label",
        "document_labels",
        ["organization_id", "label"],
    )
    bind = op.get_bind()
    bind.exec_driver_sql(
        "ALTER TABLE document_labels ENABLE ROW LEVEL SECURITY"
    )
    bind.exec_driver_sql(
        "DROP POLICY IF EXISTS trustseal_tenant_isolation ON document_labels"
    )
    bind.exec_driver_sql(
        "CREATE POLICY trustseal_tenant_isolation ON document_labels "
        "USING (trustseal_tenant_match(organization_id)) "
        "WITH CHECK (trustseal_tenant_match(organization_id))"
    )


def downgrade():
    bind = op.get_bind()
    bind.exec_driver_sql(
        "DROP POLICY IF EXISTS trustseal_tenant_isolation ON document_labels"
    )
    bind.exec_driver_sql(
        "ALTER TABLE document_labels DISABLE ROW LEVEL SECURITY"
    )
    op.drop_index("ix_document_labels_org_label", table_name="document_labels")
    op.drop_index("ix_document_labels_organization_id", table_name="document_labels")
    op.drop_index("ix_document_labels_document_id", table_name="document_labels")
    op.drop_table("document_labels")
