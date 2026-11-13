"""Append-only detached RFC 3161 timestamps.

Revision ID: q1f539d4a2c0
Revises: p0e428c3f1b9
"""
from alembic import op
import sqlalchemy as sa

revision = "q1f539d4a2c0"
down_revision = "p0e428c3f1b9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "evidence_timestamps",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("retention_id", sa.BigInteger(), sa.ForeignKey("evidence_retentions.id"), nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("operator_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("artifact_sha256", sa.String(64), nullable=False),
        sa.Column("tsa_certificate_sha256", sa.String(64), nullable=False),
        sa.Column("token_sha256", sa.String(64), nullable=False),
        sa.Column("token_der_b64", sa.Text(), nullable=False),
        sa.Column("gen_time", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("retention_id", "token_sha256", name="uq_evidence_timestamp_token"),
    )
    op.create_index("ix_evidence_timestamps_retention_id", "evidence_timestamps", ["retention_id"])
    op.create_index("ix_evidence_timestamps_organization_id", "evidence_timestamps", ["organization_id"])
    op.execute("""
        CREATE TRIGGER trg_evidence_timestamps_append_only
        BEFORE UPDATE OR DELETE ON evidence_timestamps
        FOR EACH ROW EXECUTE FUNCTION trustseal_reject_snapshot_mutation()
    """)


def downgrade():
    raise RuntimeError("Retained RFC 3161 timestamp evidence cannot be destructively downgraded")
