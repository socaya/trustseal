"""Cross-record integrity checks for signer review evidence.

Revision ID: f2a91d6e4b80
Revises: e1a904f7b2c6
"""
from alembic import op

revision = "f2a91d6e4b80"
down_revision = "e1a904f7b2c6"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE FUNCTION trustseal_validate_signer_decision()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            ch signer_challenges%ROWTYPE;
            part envelope_participants%ROWTYPE;
            env signing_envelopes%ROWTYPE;
        BEGIN
            SELECT * INTO ch FROM signer_challenges WHERE id = NEW.challenge_id FOR SHARE;
            SELECT * INTO part FROM envelope_participants WHERE id = NEW.participant_id FOR SHARE;
            SELECT * INTO env FROM signing_envelopes WHERE id = NEW.envelope_id FOR SHARE;

            IF NOT FOUND OR ch.id IS NULL OR part.id IS NULL OR env.id IS NULL
                OR ch.consumed_at IS NULL
                OR ch.consumed_at > ch.expires_at
                OR ch.envelope_id <> NEW.envelope_id
                OR ch.participant_id <> NEW.participant_id
                OR ch.user_id <> NEW.user_id
                OR ch.document_sha256 <> NEW.document_sha256
                OR part.envelope_id <> NEW.envelope_id
                OR part.user_id <> NEW.user_id
                OR env.document_sha256 <> NEW.document_sha256
                OR env.state <> 'prepared'
            THEN
                RAISE EXCEPTION 'signer review evidence does not match bound challenge';
            END IF;
            RETURN NEW;
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_validate_signer_decision
        BEFORE INSERT ON signer_decisions
        FOR EACH ROW EXECUTE FUNCTION trustseal_validate_signer_decision()
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_validate_signer_decision ON signer_decisions")
    op.execute("DROP FUNCTION IF EXISTS trustseal_validate_signer_decision()")
