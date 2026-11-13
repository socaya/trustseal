"""Create immutable post-signature DSS derivatives.

Revision ID: v6e084c9f7b5
Revises: u5d973b8e6a4
"""
from alembic import op
import sqlalchemy as sa

revision = "v6e084c9f7b5"
down_revision = "u5d973b8e6a4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pdf_dss_derivatives",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("retention_id", sa.BigInteger(), sa.ForeignKey("evidence_retentions.id"), nullable=False),
        sa.Column("dossier_id", sa.BigInteger(), sa.ForeignKey("validation_dossiers.id"), nullable=False, unique=True),
        sa.Column("operator_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("dossier_sha256", sa.String(64), nullable=False),
        sa.Column("object_key", sa.String(96), nullable=False, unique=True),
        sa.Column("output_sha256", sa.String(64), nullable=False),
        sa.Column("output_size", sa.BigInteger(), nullable=False),
        sa.Column("profile", sa.String(60), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("output_size > 0", name="ck_pdf_dss_derivative_size"),
        sa.CheckConstraint(
            "profile = 'dss_evidence_only_not_pades_lt'",
            name="ck_pdf_dss_derivative_profile",
        ),
    )
    op.create_index("ix_pdf_dss_derivatives_organization_id", "pdf_dss_derivatives", ["organization_id"])
    op.create_index("ix_pdf_dss_derivatives_retention_id", "pdf_dss_derivatives", ["retention_id"])
    op.execute("""
        CREATE TRIGGER trg_pdf_dss_derivatives_append_only
        BEFORE UPDATE OR DELETE ON pdf_dss_derivatives
        FOR EACH ROW EXECUTE FUNCTION trustseal_reject_snapshot_mutation()
    """)


def downgrade():
    raise RuntimeError("Immutable PDF DSS derivatives cannot be destructively downgraded")
