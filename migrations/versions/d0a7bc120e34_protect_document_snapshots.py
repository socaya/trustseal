"""Enforce append-only draft snapshots at the PostgreSQL layer.

Revision ID: d0a7bc120e34
Revises: c6e8a2f74109
"""
from alembic import op

revision = "d0a7bc120e34"
down_revision = "c6e8a2f74109"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE FUNCTION trustseal_reject_snapshot_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'document snapshots are append-only'
                USING ERRCODE = '23514';
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_document_snapshots_append_only
        BEFORE UPDATE OR DELETE ON document_snapshots
        FOR EACH ROW
        EXECUTE FUNCTION trustseal_reject_snapshot_mutation();
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_document_snapshots_append_only ON document_snapshots")
    op.execute("DROP FUNCTION IF EXISTS trustseal_reject_snapshot_mutation()")
