"""Governed tenant stamp custody and immutable issuance.

Revision ID: l6a084e9b7d5
Revises: k5f973d8a6c4
"""
from alembic import op
import sqlalchemy as sa

revision = "l6a084e9b7d5"
down_revision = "k5f973d8a6c4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "managed_stamps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("custodian_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime()),
        sa.Column("revoked_by_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("revoked_at", sa.DateTime()),
        sa.UniqueConstraint("organization_id", "code", name="uq_managed_stamp_org_code"),
        sa.CheckConstraint("status IN ('pending','active','revoked')", name="ck_managed_stamp_status"),
    )
    op.create_index("ix_managed_stamps_organization_id", "managed_stamps", ["organization_id"])
    op.create_table(
        "stamp_applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stamp_id", sa.Integer(), sa.ForeignKey("managed_stamps.id"), nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("finalized_pdf_id", sa.BigInteger(), sa.ForeignKey("finalized_pdfs.id"), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("evidence_sha256", sa.String(64), nullable=False),
        sa.Column("requested_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.String(240), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("decided_by_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("decided_at", sa.DateTime()),
        sa.UniqueConstraint("stamp_id", "finalized_pdf_id", name="uq_stamp_application_pdf"),
        sa.CheckConstraint("status IN ('pending','approved','rejected')", name="ck_stamp_application_status"),
    )
    op.create_index("ix_stamp_applications_stamp_id", "stamp_applications", ["stamp_id"])
    op.create_index("ix_stamp_applications_organization_id", "stamp_applications", ["organization_id"])
    op.create_table(
        "stamp_attestations",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("application_id", sa.Integer(), sa.ForeignKey("stamp_applications.id"), nullable=False, unique=True),
        sa.Column("stamp_id", sa.Integer(), sa.ForeignKey("managed_stamps.id"), nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("operator_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("algorithm", sa.String(16), nullable=False),
        sa.Column("key_id", sa.String(80), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_stamp_attestations_organization_id", "stamp_attestations", ["organization_id"])
    op.execute("""
        CREATE TRIGGER trg_stamp_attestations_append_only
        BEFORE UPDATE OR DELETE ON stamp_attestations
        FOR EACH ROW EXECUTE FUNCTION trustseal_reject_snapshot_mutation()
    """)
    # Reject identity alterations, stamp reactivation and decided request edits.
    op.execute("""
        CREATE FUNCTION trustseal_managed_stamp_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'managed stamp records cannot be deleted';
          END IF;
          IF NEW.id IS DISTINCT FROM OLD.id
             OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
             OR NEW.code IS DISTINCT FROM OLD.code
             OR NEW.name IS DISTINCT FROM OLD.name
             OR NEW.custodian_id IS DISTINCT FROM OLD.custodian_id
             OR NEW.created_by_id IS DISTINCT FROM OLD.created_by_id
             OR NEW.created_at IS DISTINCT FROM OLD.created_at
             OR (OLD.status = 'pending' AND NEW.status NOT IN ('pending','active','revoked'))
             OR (OLD.status = 'active' AND NEW.status NOT IN ('active','revoked'))
             OR (OLD.status = 'revoked' AND NEW IS DISTINCT FROM OLD)
             OR (OLD.status = 'active' AND NEW.approved_by_id IS DISTINCT FROM OLD.approved_by_id)
          THEN
            RAISE EXCEPTION 'illegal managed stamp mutation';
          END IF;
          RETURN NEW;
        END; $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_managed_stamp_guard
        BEFORE UPDATE OR DELETE ON managed_stamps
        FOR EACH ROW EXECUTE FUNCTION trustseal_managed_stamp_guard()
    """)
    op.execute("""
        CREATE FUNCTION trustseal_stamp_application_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'stamp requests cannot be deleted';
          END IF;
          IF to_jsonb(NEW) - 'status' - 'decided_by_id' - 'decided_at'
             IS DISTINCT FROM
             to_jsonb(OLD) - 'status' - 'decided_by_id' - 'decided_at'
             OR OLD.status <> 'pending'
             OR NEW.status NOT IN ('approved','rejected')
             OR NEW.decided_by_id IS NULL OR NEW.decided_at IS NULL
          THEN
            RAISE EXCEPTION 'stamp request is immutable after decision';
          END IF;
          RETURN NEW;
        END; $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_stamp_application_guard
        BEFORE UPDATE OR DELETE ON stamp_applications
        FOR EACH ROW EXECUTE FUNCTION trustseal_stamp_application_guard()
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_stamp_application_guard ON stamp_applications")
    op.execute("DROP FUNCTION IF EXISTS trustseal_stamp_application_guard()")
    op.execute("DROP TRIGGER IF EXISTS trg_managed_stamp_guard ON managed_stamps")
    op.execute("DROP FUNCTION IF EXISTS trustseal_managed_stamp_guard()")
    op.execute("DROP TRIGGER IF EXISTS trg_stamp_attestations_append_only ON stamp_attestations")
    op.drop_index("ix_stamp_attestations_organization_id", table_name="stamp_attestations")
    op.drop_table("stamp_attestations")
    op.drop_index("ix_stamp_applications_organization_id", table_name="stamp_applications")
    op.drop_index("ix_stamp_applications_stamp_id", table_name="stamp_applications")
    op.drop_table("stamp_applications")
    op.drop_index("ix_managed_stamps_organization_id", table_name="managed_stamps")
    op.drop_table("managed_stamps")
