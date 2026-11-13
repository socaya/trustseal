"""Append-only certificate revocation evidence.

Revision ID: r2a640e5b3d1
Revises: q1f539d4a2c0
"""
from alembic import op
import sqlalchemy as sa

revision = "r2a640e5b3d1"
down_revision = "q1f539d4a2c0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "certificate_revocation_evidence",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("timestamp_id", sa.BigInteger(), sa.ForeignKey("evidence_timestamps.id"), nullable=False),
        sa.Column("operator_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("subject_certificate_sha256", sa.String(64), nullable=False),
        sa.Column("issuer_certificate_sha256", sa.String(64), nullable=False),
        sa.Column("crl_sha256", sa.String(64), nullable=False),
        sa.Column("crl_der_b64", sa.Text(), nullable=False),
        sa.Column("subject_der_b64", sa.Text(), nullable=False),
        sa.Column("issuer_der_b64", sa.Text(), nullable=False),
        sa.Column("this_update", sa.DateTime(), nullable=False),
        sa.Column("next_update", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("timestamp_id", "crl_sha256", name="uq_revocation_timestamp_crl"),
        sa.CheckConstraint("status IN ('good','revoked')", name="ck_revocation_evidence_status"),
        sa.CheckConstraint("next_update > this_update", name="ck_revocation_evidence_window"),
    )
    op.create_index("ix_revocation_org", "certificate_revocation_evidence", ["organization_id"])
    op.create_index("ix_revocation_timestamp", "certificate_revocation_evidence", ["timestamp_id"])
    op.execute("""
        CREATE TRIGGER trg_revocation_evidence_append_only
        BEFORE UPDATE OR DELETE ON certificate_revocation_evidence
        FOR EACH ROW EXECUTE FUNCTION trustseal_reject_snapshot_mutation()
    """)


def downgrade():
    raise RuntimeError("Cannot destructively downgrade retained certificate status evidence")
