"""Immutable retention/hold ledger and signed integrity checkpoints.

Revision ID: o9d317b2e0a8
Revises: n8c206a1d9f7
"""
from alembic import op
import sqlalchemy as sa

revision = "o9d317b2e0a8"
down_revision = "n8c206a1d9f7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "evidence_retentions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("artifact_type", sa.String(24), nullable=False),
        sa.Column("artifact_id", sa.BigInteger(), nullable=False),
        sa.Column("artifact_sha256", sa.String(64), nullable=False),
        sa.Column("retain_until", sa.DateTime(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("artifact_type", "artifact_id", name="uq_evidence_retention_artifact"),
        sa.CheckConstraint("artifact_type IN ('finalized_pdf','stamped_pdf')", name="ck_evidence_retention_type"),
    )
    op.create_index("ix_evidence_retentions_organization_id", "evidence_retentions", ["organization_id"])
    op.create_table(
        "evidence_legal_holds",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("retention_id", sa.BigInteger(), sa.ForeignKey("evidence_retentions.id"), nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("requested_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("released_by_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("released_at", sa.DateTime()),
        sa.CheckConstraint(
            "(released_by_id IS NULL AND released_at IS NULL) OR "
            "(released_by_id IS NOT NULL AND released_at IS NOT NULL)",
            name="ck_evidence_hold_release",
        ),
    )
    op.create_index("ix_evidence_legal_holds_retention_id", "evidence_legal_holds", ["retention_id"])
    op.create_index("ix_evidence_legal_holds_organization_id", "evidence_legal_holds", ["organization_id"])
    op.create_table(
        "evidence_checkpoints",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("retention_id", sa.BigInteger(), sa.ForeignKey("evidence_retentions.id"), nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("operator_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("algorithm", sa.String(16), nullable=False),
        sa.Column("key_id", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_evidence_checkpoints_retention_id", "evidence_checkpoints", ["retention_id"])
    op.create_index("ix_evidence_checkpoints_organization_id", "evidence_checkpoints", ["organization_id"])
    for table in ("evidence_retentions", "evidence_checkpoints"):
        op.execute("""
            CREATE TRIGGER trg_%s_append_only
            BEFORE UPDATE OR DELETE ON %s
            FOR EACH ROW EXECUTE FUNCTION trustseal_reject_snapshot_mutation()
        """ % (table, table))
    op.execute("""
      CREATE FUNCTION trustseal_legal_hold_release_only()
      RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP = 'DELETE' THEN
          RAISE EXCEPTION 'legal hold cannot be deleted';
        END IF;
        IF to_jsonb(NEW) - 'released_by_id' - 'released_at'
           IS DISTINCT FROM to_jsonb(OLD) - 'released_by_id' - 'released_at'
           OR OLD.released_at IS NOT NULL
           OR NEW.released_at IS NULL
           OR NEW.released_by_id IS NULL
           OR NEW.released_at < OLD.requested_at
           OR NEW.released_by_id = OLD.requested_by_id
        THEN
          RAISE EXCEPTION 'legal hold release requires independent operator';
        END IF;
        RETURN NEW;
      END; $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_evidence_hold_release_only
        BEFORE UPDATE OR DELETE ON evidence_legal_holds
        FOR EACH ROW EXECUTE FUNCTION trustseal_legal_hold_release_only()
    """)


def downgrade():
    raise RuntimeError("Evidence preservation and hold history cannot be destructively downgraded")
