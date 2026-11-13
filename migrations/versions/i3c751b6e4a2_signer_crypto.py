"""Signer-held public key possession and detached endorsement tables.

Revision ID: i3c751b6e4a2
Revises: h2b640a1d8f3
"""
from alembic import op
import sqlalchemy as sa

revision = "i3c751b6e4a2"
down_revision = "h2b640a1d8f3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "signer_public_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("public_key_pem", sa.Text(), nullable=False),
        sa.Column("activated_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime()),
        sa.CheckConstraint("revoked_at IS NULL OR revoked_at >= activated_at", name="ck_signer_key_revocation_time"),
    )
    op.create_index("ix_signer_public_keys_user_id", "signer_public_keys", ["user_id"])
    op.create_index("ix_signer_public_keys_organization_id", "signer_public_keys", ["organization_id"])
    op.create_table(
        "signer_key_challenges",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("public_key_pem", sa.Text(), nullable=False),
        sa.Column("nonce_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime()),
    )
    op.create_table(
        "signer_endorsement_challenges",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("envelope_id", sa.Integer(), sa.ForeignKey("signing_envelopes.id"), nullable=False),
        sa.Column("participant_id", sa.Integer(), sa.ForeignKey("envelope_participants.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("signer_key_id", sa.Integer(), sa.ForeignKey("signer_public_keys.id"), nullable=False),
        sa.Column("nonce_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("signed_payload", sa.JSON(), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime()),
    )
    op.create_index("ix_signer_endorsement_challenges_envelope_user",
                    "signer_endorsement_challenges", ["envelope_id", "user_id"])
    op.create_table(
        "signer_endorsements",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("envelope_id", sa.Integer(), sa.ForeignKey("signing_envelopes.id"), nullable=False),
        sa.Column("participant_id", sa.Integer(), sa.ForeignKey("envelope_participants.id"),
                  nullable=False, unique=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("signer_key_id", sa.Integer(), sa.ForeignKey("signer_public_keys.id"), nullable=False),
        sa.Column("challenge_id", sa.BigInteger(),
                  sa.ForeignKey("signer_endorsement_challenges.id"), nullable=False, unique=True),
        sa.Column("signed_payload", sa.JSON(), nullable=False),
        sa.Column("signature_b64", sa.Text(), nullable=False),
        sa.Column("signed_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_signer_endorsements_envelope_id", "signer_endorsements", ["envelope_id"])
    op.execute("""
        CREATE TRIGGER trg_signer_endorsements_append_only
        BEFORE UPDATE OR DELETE ON signer_endorsements
        FOR EACH ROW EXECUTE FUNCTION trustseal_reject_snapshot_mutation()
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_signer_endorsements_append_only ON signer_endorsements")
    op.drop_index("ix_signer_endorsements_envelope_id", table_name="signer_endorsements")
    op.drop_table("signer_endorsements")
    op.drop_index("ix_signer_endorsement_challenges_envelope_user",
                  table_name="signer_endorsement_challenges")
    op.drop_table("signer_endorsement_challenges")
    op.drop_table("signer_key_challenges")
    op.drop_index("ix_signer_public_keys_organization_id", table_name="signer_public_keys")
    op.drop_index("ix_signer_public_keys_user_id", table_name="signer_public_keys")
    op.drop_table("signer_public_keys")
