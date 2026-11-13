"""Authenticated signer intent challenges and append-only decisions.

Revision ID: d8e520c743ab
Revises: c8d192f4a610
"""
from alembic import op
import sqlalchemy as sa

revision = "d8e520c743ab"
down_revision = "c8d192f4a610"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "signer_challenges",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("envelope_id", sa.Integer(), sa.ForeignKey("signing_envelopes.id"), nullable=False),
        sa.Column("participant_id", sa.Integer(), sa.ForeignKey("envelope_participants.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("nonce_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("document_sha256", sa.String(64), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime()),
        sa.CheckConstraint("expires_at > issued_at", name="ck_signer_challenge_expiry"),
    )
    op.create_index("ix_signer_challenges_envelope_id", "signer_challenges", ["envelope_id"])
    op.create_index("ix_signer_challenges_participant_user_issued", "signer_challenges", ["participant_id", "user_id", "issued_at"])
    op.create_table(
        "signer_decisions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("envelope_id", sa.Integer(), sa.ForeignKey("signing_envelopes.id"), nullable=False),
        sa.Column("participant_id", sa.Integer(), sa.ForeignKey("envelope_participants.id"), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("challenge_id", sa.BigInteger(), sa.ForeignKey("signer_challenges.id"), nullable=False, unique=True),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("document_sha256", sa.String(64), nullable=False),
        sa.Column("consent_version", sa.String(32), nullable=False),
        sa.Column("consent_sha256", sa.String(64), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("decision IN ('acknowledged','declined')", name="ck_signer_decision_value"),
    )
    op.create_index("ix_signer_decisions_envelope_id", "signer_decisions", ["envelope_id"])
    op.execute("""
        CREATE TRIGGER trg_signer_decisions_append_only
        BEFORE UPDATE OR DELETE ON signer_decisions
        FOR EACH ROW EXECUTE FUNCTION trustseal_reject_snapshot_mutation()
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_signer_decisions_append_only ON signer_decisions")
    op.drop_index("ix_signer_decisions_envelope_id", table_name="signer_decisions")
    op.drop_table("signer_decisions")
    op.drop_index("ix_signer_challenges_participant_user_issued", table_name="signer_challenges")
    op.drop_index("ix_signer_challenges_envelope_id", table_name="signer_challenges")
    op.drop_table("signer_challenges")
