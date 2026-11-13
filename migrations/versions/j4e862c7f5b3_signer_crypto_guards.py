"""Enforce signer-held credential/endorsement invariants at the DB layer.

Revision ID: j4e862c7f5b3
Revises: i3c751b6e4a2
"""
from alembic import op

revision = "j4e862c7f5b3"
down_revision = "i3c751b6e4a2"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
      CREATE FUNCTION trustseal_signer_public_key_guard()
      RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP = 'DELETE' THEN
          RAISE EXCEPTION 'registered signer keys cannot be deleted';
        END IF;
        IF NEW.id IS DISTINCT FROM OLD.id
           OR NEW.user_id IS DISTINCT FROM OLD.user_id
           OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
           OR NEW.fingerprint IS DISTINCT FROM OLD.fingerprint
           OR NEW.public_key_pem IS DISTINCT FROM OLD.public_key_pem
           OR NEW.activated_at IS DISTINCT FROM OLD.activated_at
           OR OLD.revoked_at IS NOT NULL
           OR NEW.revoked_at IS NULL THEN
          RAISE EXCEPTION 'signer public keys may only be revoked once';
        END IF;
        RETURN NEW;
      END; $$;
    """)
    op.execute("""
      CREATE TRIGGER trg_signer_public_keys_guard
      BEFORE UPDATE OR DELETE ON signer_public_keys
      FOR EACH ROW EXECUTE FUNCTION trustseal_signer_public_key_guard()
    """)
    for table in ("signer_key_challenges", "signer_endorsement_challenges"):
        op.execute("""
          CREATE TRIGGER trg_%s_consume_once
          BEFORE UPDATE OR DELETE ON %s
          FOR EACH ROW EXECUTE FUNCTION trustseal_challenge_consume_only()
        """ % (table, table))
    # The older challenge guard refers to columns belonging to signer_challenges,
    # so the above triggers are replaced below with a generic row-level guard.
    for table in ("signer_key_challenges", "signer_endorsement_challenges"):
        op.execute("DROP TRIGGER trg_%s_consume_once ON %s" % (table, table))
    op.execute("""
      CREATE FUNCTION trustseal_crypto_challenge_guard()
      RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP = 'DELETE' THEN
          RAISE EXCEPTION 'key challenges cannot be removed';
        END IF;
        IF to_jsonb(NEW) - 'consumed_at' IS DISTINCT FROM
           to_jsonb(OLD) - 'consumed_at'
           OR OLD.consumed_at IS NOT NULL
           OR NEW.consumed_at IS NULL
           OR NEW.consumed_at < OLD.issued_at THEN
          RAISE EXCEPTION 'challenge can only be consumed once';
        END IF;
        RETURN NEW;
      END; $$;
    """)
    for table in ("signer_key_challenges", "signer_endorsement_challenges"):
        op.execute("""
          CREATE TRIGGER trg_%s_consume_once
          BEFORE UPDATE OR DELETE ON %s
          FOR EACH ROW EXECUTE FUNCTION trustseal_crypto_challenge_guard()
        """ % (table, table))
    op.execute("""
      CREATE FUNCTION trustseal_endorsement_consistency()
      RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE
        c signer_endorsement_challenges%%ROWTYPE;
        k signer_public_keys%%ROWTYPE;
        p envelope_participants%%ROWTYPE;
        e signing_envelopes%%ROWTYPE;
        d signer_decisions%%ROWTYPE;
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
           OR c.signed_payload IS DISTINCT FROM NEW.signed_payload
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
    op.execute("""
      CREATE TRIGGER trg_signer_endorsement_consistency
      BEFORE INSERT ON signer_endorsements
      FOR EACH ROW EXECUTE FUNCTION trustseal_endorsement_consistency()
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_signer_endorsement_consistency ON signer_endorsements")
    op.execute("DROP FUNCTION IF EXISTS trustseal_endorsement_consistency()")
    for table in ("signer_key_challenges", "signer_endorsement_challenges"):
        op.execute("DROP TRIGGER IF EXISTS trg_%s_consume_once ON %s" % (table, table))
    op.execute("DROP FUNCTION IF EXISTS trustseal_crypto_challenge_guard()")
    op.execute("DROP TRIGGER IF EXISTS trg_signer_public_keys_guard ON signer_public_keys")
    op.execute("DROP FUNCTION IF EXISTS trustseal_signer_public_key_guard()")
