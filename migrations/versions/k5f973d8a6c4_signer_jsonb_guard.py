"""Fix PostgreSQL JSON comparison in signer endorsement integrity guard.

Revision ID: k5f973d8a6c4
Revises: j4e862c7f5b3
"""
from alembic import op

revision = "k5f973d8a6c4"
down_revision = "j4e862c7f5b3"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
      CREATE OR REPLACE FUNCTION trustseal_endorsement_consistency()
      RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE
        c signer_endorsement_challenges%ROWTYPE;
        k signer_public_keys%ROWTYPE;
        p envelope_participants%ROWTYPE;
        e signing_envelopes%ROWTYPE;
        d signer_decisions%ROWTYPE;
      BEGIN
        SELECT * INTO c FROM signer_endorsement_challenges
          WHERE id = NEW.challenge_id FOR SHARE;
        SELECT * INTO k FROM signer_public_keys
          WHERE id = NEW.signer_key_id FOR SHARE;
        SELECT * INTO p FROM envelope_participants
          WHERE id = NEW.participant_id FOR SHARE;
        SELECT * INTO e FROM signing_envelopes
          WHERE id = NEW.envelope_id FOR SHARE;
        SELECT * INTO d FROM signer_decisions
          WHERE participant_id = NEW.participant_id FOR SHARE;
        IF c.id IS NULL OR k.id IS NULL OR p.id IS NULL
           OR e.id IS NULL OR d.id IS NULL
           OR c.consumed_at IS NULL OR c.consumed_at > c.expires_at
           OR c.envelope_id <> NEW.envelope_id
           OR c.participant_id <> NEW.participant_id
           OR c.user_id <> NEW.user_id
           OR c.signer_key_id <> NEW.signer_key_id
           OR (c.signed_payload::jsonb IS DISTINCT FROM NEW.signed_payload::jsonb)
           OR p.envelope_id <> NEW.envelope_id OR p.user_id <> NEW.user_id
           OR k.user_id <> NEW.user_id
           OR k.organization_id <> e.organization_id
           OR k.revoked_at IS NOT NULL
           OR e.state <> 'prepared'
           OR d.decision <> 'acknowledged'
           OR d.user_id <> NEW.user_id
           OR d.document_sha256 <> e.document_sha256
        THEN
           RAISE EXCEPTION 'signer endorsement evidence inconsistent';
        END IF;
        RETURN NEW;
      END; $$;
    """)


def downgrade():
    # Reintroducing a broken integrity check is not safe for evidence records.
    raise RuntimeError("Signer evidence integrity fix cannot be safely downgraded")
