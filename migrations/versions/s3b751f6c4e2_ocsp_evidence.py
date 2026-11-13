"""Retain verified OCSP response bytes and certificate evidence.

Revision ID: s3b751f6c4e2
Revises: r2a640e5b3d1
"""
from alembic import op
import sqlalchemy as sa

revision = "s3b751f6c4e2"
down_revision = "r2a640e5b3d1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ocsp_evidence",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("timestamp_id", sa.BigInteger(), sa.ForeignKey("evidence_timestamps.id"), nullable=False),
        sa.Column("operator_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("subject_certificate_sha256", sa.String(64), nullable=False),
        sa.Column("issuer_certificate_sha256", sa.String(64), nullable=False),
        sa.Column("response_sha256", sa.String(64), nullable=False),
        sa.Column("response_der_b64", sa.Text(), nullable=False),
        sa.Column("subject_der_b64", sa.Text(), nullable=False),
        sa.Column("issuer_der_b64", sa.Text(), nullable=False),
        sa.Column("produced_at", sa.DateTime(), nullable=False),
        sa.Column("this_update", sa.DateTime(), nullable=False),
        sa.Column("next_update", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("timestamp_id", "response_sha256", name="uq_ocsp_timestamp_response"),
        sa.CheckConstraint("status IN ('good','revoked','unknown')", name="ck_ocsp_status"),
        sa.CheckConstraint("next_update > this_update", name="ck_ocsp_window"),
    )
    op.create_index("ix_ocsp_org", "ocsp_evidence", ["organization_id"])
    op.create_index("ix_ocsp_timestamp", "ocsp_evidence", ["timestamp_id"])
    op.execute("""
        CREATE TRIGGER trg_ocsp_evidence_append_only
        BEFORE UPDATE OR DELETE ON ocsp_evidence
        FOR EACH ROW EXECUTE FUNCTION trustseal_reject_snapshot_mutation()
    """)


def downgrade():
    raise RuntimeError("OCSP evidence history cannot be destructively downgraded")
