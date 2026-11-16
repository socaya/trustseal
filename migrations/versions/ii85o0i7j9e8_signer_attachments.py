"""Signer-uploaded supporting attachments (Phase U1).

Revision ID: ii85o0i7j9e8
Revises: hh74n9h6i8d7
"""
from alembic import op
import sqlalchemy as sa

revision = "ii85o0i7j9e8"
down_revision = "hh74n9h6i8d7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "signer_attachments",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "envelope_id",
            sa.Integer,
            sa.ForeignKey("signing_envelopes.id"),
            nullable=False,
        ),
        sa.Column(
            "participant_id",
            sa.Integer,
            sa.ForeignKey("envelope_participants.id"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "decision_id",
            sa.BigInteger,
            sa.ForeignKey("signer_decisions.id"),
            nullable=True,
        ),
        sa.Column(
            "organization_id",
            sa.Integer,
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("object_key", sa.String(200), nullable=False, unique=True),
        sa.Column("file_name", sa.String(200), nullable=False),
        sa.Column("mime_type", sa.String(80), nullable=False),
        sa.Column("file_size", sa.Integer, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("scanner", sa.String(60), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "file_size > 0 AND file_size <= 10485760",
            name="ck_signer_attachment_size",
        ),
        sa.CheckConstraint(
            "mime_type IN ('application/pdf','image/png','image/jpeg')",
            name="ck_signer_attachment_mime",
        ),
        sa.CheckConstraint(
            "char_length(file_name) >= 1 AND char_length(file_name) <= 200",
            name="ck_signer_attachment_name_length",
        ),
    )
    op.create_index(
        "ix_signer_attachments_envelope_id",
        "signer_attachments",
        ["envelope_id"],
    )
    op.create_index(
        "ix_signer_attachments_organization_id",
        "signer_attachments",
        ["organization_id"],
    )
    op.create_index(
        "ix_signer_attachments_decision_id",
        "signer_attachments",
        ["decision_id"],
    )
    # RLS matches the shared pattern via ``trustseal_tenant_match``.
    bind = op.get_bind()
    bind.exec_driver_sql(
        "ALTER TABLE signer_attachments ENABLE ROW LEVEL SECURITY"
    )
    bind.exec_driver_sql(
        "DROP POLICY IF EXISTS trustseal_tenant_isolation ON signer_attachments"
    )
    bind.exec_driver_sql(
        "CREATE POLICY trustseal_tenant_isolation ON signer_attachments "
        "USING (trustseal_tenant_match(organization_id)) "
        "WITH CHECK (trustseal_tenant_match(organization_id))"
    )


def downgrade():
    bind = op.get_bind()
    bind.exec_driver_sql(
        "DROP POLICY IF EXISTS trustseal_tenant_isolation ON signer_attachments"
    )
    bind.exec_driver_sql(
        "ALTER TABLE signer_attachments DISABLE ROW LEVEL SECURITY"
    )
    op.drop_index(
        "ix_signer_attachments_decision_id",
        table_name="signer_attachments",
    )
    op.drop_index(
        "ix_signer_attachments_organization_id",
        table_name="signer_attachments",
    )
    op.drop_index(
        "ix_signer_attachments_envelope_id",
        table_name="signer_attachments",
    )
    op.drop_table("signer_attachments")
