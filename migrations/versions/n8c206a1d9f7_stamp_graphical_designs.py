"""Versioned stamp artwork and immutable decisions.

Revision ID: n8c206a1d9f7
Revises: m7b195f0c8e6
"""
from alembic import op
import sqlalchemy as sa

revision = "n8c206a1d9f7"
down_revision = "m7b195f0c8e6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stamp_design_versions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("stamp_id", sa.Integer(), sa.ForeignKey("managed_stamps.id"), nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("layout", sa.JSON(), nullable=False),
        sa.Column("logo_png_b64", sa.Text()),
        sa.Column("logo_sha256", sa.String(64)),
        sa.Column("design_sha256", sa.String(64), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_at", sa.DateTime()),
        sa.UniqueConstraint("stamp_id", "version", name="uq_stamp_design_version"),
        sa.CheckConstraint("version > 0", name="ck_stamp_design_version"),
        sa.CheckConstraint("state IN ('pending','approved','rejected')", name="ck_stamp_design_state"),
    )
    op.create_index("ix_stamp_design_versions_stamp_id", "stamp_design_versions", ["stamp_id"])
    op.create_index("ix_stamp_design_versions_organization_id", "stamp_design_versions", ["organization_id"])
    op.execute("""
        CREATE FUNCTION trustseal_stamp_design_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'stamp designs may not be deleted';
            END IF;
            IF OLD.state <> 'pending'
               OR NEW.state NOT IN ('approved', 'rejected')
               OR NEW.approved_by_id IS NULL OR NEW.approved_at IS NULL
               OR to_jsonb(NEW) - 'state' - 'approved_by_id' - 'approved_at'
                  IS DISTINCT FROM
                  to_jsonb(OLD) - 'state' - 'approved_by_id' - 'approved_at'
            THEN
                RAISE EXCEPTION 'stamp design is immutable after submission';
            END IF;
            RETURN NEW;
        END; $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_stamp_design_guard
        BEFORE UPDATE OR DELETE ON stamp_design_versions
        FOR EACH ROW EXECUTE FUNCTION trustseal_stamp_design_guard()
    """)
    op.add_column("stamped_pdfs", sa.Column("design_version_id", sa.BigInteger(),
                  sa.ForeignKey("stamp_design_versions.id"), nullable=True))
    op.add_column("stamped_pdfs", sa.Column("design_sha256", sa.String(64), nullable=True))


def downgrade():
    raise RuntimeError("Cannot safely remove immutable design evidence from signed PDFs")
