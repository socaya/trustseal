"""Envelope routing modes + withdrawal + preview checkpoint.

Revision ID: o5a084c9e8f5
Revises: n4f973b8d7e4

Adds routing_mode ('sequential' | 'parallel' | 'quorum'), optional
quorum_required count, withdrawal metadata, and preview_confirmed_at
to the SigningEnvelope. Replaces the state CHECK constraint to admit
the new 'withdrawn' state.
"""
from alembic import op
import sqlalchemy as sa

revision = "o5a084c9e8f5"
down_revision = "n4f973b8d7e4"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE signing_envelopes "
        "ADD COLUMN IF NOT EXISTS routing_mode VARCHAR(20) "
        "NOT NULL DEFAULT 'sequential'"
    )
    op.execute(
        "ALTER TABLE signing_envelopes "
        "ADD COLUMN IF NOT EXISTS quorum_required INTEGER"
    )
    op.execute(
        "ALTER TABLE signing_envelopes "
        "ADD COLUMN IF NOT EXISTS preview_confirmed_at TIMESTAMP"
    )
    op.execute(
        "ALTER TABLE signing_envelopes "
        "ADD COLUMN IF NOT EXISTS withdrawn_at TIMESTAMP"
    )
    op.execute(
        "ALTER TABLE signing_envelopes "
        "ADD COLUMN IF NOT EXISTS withdrawn_by_id INTEGER "
        "REFERENCES users(id)"
    )
    op.execute(
        "ALTER TABLE signing_envelopes "
        "ADD COLUMN IF NOT EXISTS withdraw_reason VARCHAR(255)"
    )
    # Replace the old state check to admit 'withdrawn'.
    op.execute(
        "ALTER TABLE signing_envelopes "
        "DROP CONSTRAINT IF EXISTS ck_envelope_preparation_state"
    )
    op.create_check_constraint(
        "ck_envelope_preparation_state",
        "signing_envelopes",
        "state IN ('draft','prepared','cancelled','withdrawn')",
    )
    op.execute(
        "ALTER TABLE signing_envelopes "
        "DROP CONSTRAINT IF EXISTS ck_envelope_routing_mode"
    )
    op.create_check_constraint(
        "ck_envelope_routing_mode",
        "signing_envelopes",
        "routing_mode IN ('sequential','parallel','quorum')",
    )
    op.execute(
        "ALTER TABLE signing_envelopes "
        "DROP CONSTRAINT IF EXISTS ck_envelope_quorum_required"
    )
    op.create_check_constraint(
        "ck_envelope_quorum_required",
        "signing_envelopes",
        "(routing_mode = 'quorum' AND quorum_required IS NOT NULL AND quorum_required > 0) "
        "OR (routing_mode <> 'quorum' AND quorum_required IS NULL)",
    )


def downgrade():
    op.drop_constraint(
        "ck_envelope_quorum_required", "signing_envelopes", type_="check"
    )
    op.drop_constraint(
        "ck_envelope_routing_mode", "signing_envelopes", type_="check"
    )
    op.drop_constraint(
        "ck_envelope_preparation_state", "signing_envelopes", type_="check"
    )
    op.create_check_constraint(
        "ck_envelope_preparation_state",
        "signing_envelopes",
        "state IN ('draft','prepared','cancelled')",
    )
    op.drop_column("signing_envelopes", "withdraw_reason")
    op.drop_column("signing_envelopes", "withdrawn_by_id")
    op.drop_column("signing_envelopes", "withdrawn_at")
    op.drop_column("signing_envelopes", "preview_confirmed_at")
    op.drop_column("signing_envelopes", "quorum_required")
    op.drop_column("signing_envelopes", "routing_mode")
