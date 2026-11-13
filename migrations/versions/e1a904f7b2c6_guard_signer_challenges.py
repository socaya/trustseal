"""Protect signer challenges and decisions after insertion.

Revision ID: e1a904f7b2c6
Revises: d8e520c743ab
"""
from alembic import op

revision = "e1a904f7b2c6"
down_revision = "d8e520c743ab"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE FUNCTION trustseal_challenge_consume_only()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'signer challenges cannot be deleted';
            END IF;
            IF NEW.id IS DISTINCT FROM OLD.id
                OR NEW.envelope_id IS DISTINCT FROM OLD.envelope_id
                OR NEW.participant_id IS DISTINCT FROM OLD.participant_id
                OR NEW.user_id IS DISTINCT FROM OLD.user_id
                OR NEW.nonce_sha256 IS DISTINCT FROM OLD.nonce_sha256
                OR NEW.document_sha256 IS DISTINCT FROM OLD.document_sha256
                OR NEW.issued_at IS DISTINCT FROM OLD.issued_at
                OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
                OR OLD.consumed_at IS NOT NULL
                OR NEW.consumed_at IS NULL
                OR NEW.consumed_at < OLD.issued_at THEN
                RAISE EXCEPTION 'signer challenge may only be consumed once';
            END IF;
            RETURN NEW;
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_signer_challenge_consume_only
        BEFORE UPDATE OR DELETE ON signer_challenges
        FOR EACH ROW EXECUTE FUNCTION trustseal_challenge_consume_only()
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_signer_challenge_consume_only ON signer_challenges")
    op.execute("DROP FUNCTION IF EXISTS trustseal_challenge_consume_only()")
