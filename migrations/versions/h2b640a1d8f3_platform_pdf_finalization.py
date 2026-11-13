"""Store immutable platform-sealed PDF artifacts.

Revision ID: h2b640a1d8f3
Revises: g1a42e05fd90
"""
from alembic import op
import sqlalchemy as sa

revision = "h2b640a1d8f3"
down_revision = "g1a42e05fd90"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "finalized_pdfs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("envelope_id", sa.Integer(), sa.ForeignKey("signing_envelopes.id"),
                  nullable=False, unique=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"),
                  nullable=False),
        sa.Column("source_blob_id", sa.Integer(), sa.ForeignKey("document_blobs.id"),
                  nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("evidence_sha256", sa.String(64), nullable=False),
        sa.Column("object_key", sa.String(96), nullable=False, unique=True),
        sa.Column("output_sha256", sa.String(64), nullable=False),
        sa.Column("output_size", sa.BigInteger(), nullable=False),
        sa.Column("certificate_sha256", sa.String(64), nullable=False),
        sa.Column("signature_field", sa.String(100), nullable=False),
        sa.Column("profile", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("output_size > 0", name="ck_finalized_pdf_size"),
    )
    op.create_index("ix_finalized_pdfs_organization_id", "finalized_pdfs", ["organization_id"])
    op.execute("""
        CREATE TRIGGER trg_finalized_pdfs_append_only
        BEFORE UPDATE OR DELETE ON finalized_pdfs
        FOR EACH ROW EXECUTE FUNCTION trustseal_reject_snapshot_mutation()
    """)
    # Lock lifecycle after a final artifact exists. This is a platform seal,
    # not a declaration that individual participants signed the document.
    op.execute("""
        CREATE FUNCTION trustseal_prevent_finalized_envelope_cancel()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.state = 'prepared' AND NEW.state = 'cancelled'
               AND EXISTS (SELECT 1 FROM finalized_pdfs WHERE envelope_id = OLD.id)
            THEN
                RAISE EXCEPTION 'cannot cancel an envelope with a finalized PDF';
            END IF;
            RETURN NEW;
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_no_cancel_finalized_envelope
        BEFORE UPDATE ON signing_envelopes
        FOR EACH ROW EXECUTE FUNCTION trustseal_prevent_finalized_envelope_cancel()
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_no_cancel_finalized_envelope ON signing_envelopes")
    op.execute("DROP FUNCTION IF EXISTS trustseal_prevent_finalized_envelope_cancel()")
    op.execute("DROP TRIGGER IF EXISTS trg_finalized_pdfs_append_only ON finalized_pdfs")
    op.drop_index("ix_finalized_pdfs_organization_id", table_name="finalized_pdfs")
    op.drop_table("finalized_pdfs")
