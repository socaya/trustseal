"""Append-only validation dossier snapshots.

Revision ID: u5d973b8e6a4
Revises: t4c862a7d5f3
"""
from alembic import op
import sqlalchemy as sa

revision = "u5d973b8e6a4"
down_revision = "t4c862a7d5f3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "validation_dossiers",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("retention_id", sa.BigInteger(), sa.ForeignKey("evidence_retentions.id"), nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("operator_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("timestamp_id", sa.BigInteger(), sa.ForeignKey("evidence_timestamps.id"), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("retention_id", "timestamp_id", "manifest_sha256",
                            name="uq_validation_dossier_snapshot"),
    )
    op.create_index("ix_validation_dossiers_retention_id", "validation_dossiers", ["retention_id"])
    op.create_index("ix_validation_dossiers_organization_id", "validation_dossiers", ["organization_id"])
    op.execute("""
        CREATE TRIGGER trg_validation_dossiers_append_only
        BEFORE UPDATE OR DELETE ON validation_dossiers
        FOR EACH ROW EXECUTE FUNCTION trustseal_reject_snapshot_mutation()
    """)


def downgrade():
    raise RuntimeError("Validation evidence history may not be destroyed")
