"""Prevent post-preparation envelope/recipient tampering via ordinary SQL.

Revision ID: c8d192f4a610
Revises: b7c104ef2a91
"""
from alembic import op

revision = "c8d192f4a610"
down_revision = "b7c104ef2a91"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE FUNCTION trustseal_envelope_participant_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE parent_state text;
        DECLARE parent_id integer;
        BEGIN
            IF TG_OP = 'UPDATE' AND NEW.envelope_id <> OLD.envelope_id THEN
                RAISE EXCEPTION 'participant envelope cannot be reassigned';
            END IF;
            IF TG_OP = 'DELETE' THEN
                parent_id := OLD.envelope_id;
            ELSE
                parent_id := NEW.envelope_id;
            END IF;
            SELECT state INTO parent_state FROM signing_envelopes
            WHERE id = parent_id FOR UPDATE;
            IF parent_state IS NULL OR parent_state <> 'draft' THEN
                RAISE EXCEPTION 'participants can only change during draft preparation';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_envelope_participant_guard
        BEFORE INSERT OR UPDATE OR DELETE ON envelope_participants
        FOR EACH ROW EXECUTE FUNCTION trustseal_envelope_participant_guard()
    """)
    op.execute("""
        CREATE FUNCTION trustseal_envelope_state_guard()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'envelopes cannot be hard-deleted';
            END IF;
            IF NEW.id <> OLD.id
                OR NEW.document_id <> OLD.document_id
                OR NEW.document_blob_id <> OLD.document_blob_id
                OR NEW.document_sha256 <> OLD.document_sha256
                OR NEW.organization_id <> OLD.organization_id
                OR NEW.created_by_id <> OLD.created_by_id THEN
                RAISE EXCEPTION 'envelope source identity is immutable';
            END IF;
            IF NOT ((OLD.state = 'draft' AND NEW.state IN ('draft','prepared','cancelled'))
                OR (OLD.state = 'prepared' AND NEW.state IN ('prepared','cancelled'))
                OR (OLD.state = 'cancelled' AND NEW.state = 'cancelled')) THEN
                RAISE EXCEPTION 'illegal envelope state transition';
            END IF;
            RETURN NEW;
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_envelope_state_guard
        BEFORE UPDATE OR DELETE ON signing_envelopes
        FOR EACH ROW EXECUTE FUNCTION trustseal_envelope_state_guard()
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_envelope_state_guard ON signing_envelopes")
    op.execute("DROP TRIGGER IF EXISTS trg_envelope_participant_guard ON envelope_participants")
    op.execute("DROP FUNCTION IF EXISTS trustseal_envelope_state_guard()")
    op.execute("DROP FUNCTION IF EXISTS trustseal_envelope_participant_guard()")
