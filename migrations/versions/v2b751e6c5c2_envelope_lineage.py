"""Envelope correction / reissue lineage.

Revision ID: v2b751e6c5c2
Revises: u1a640d5b4b1
"""
from alembic import op
import sqlalchemy as sa

revision = "v2b751e6c5c2"
down_revision = "u1a640d5b4b1"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE signing_envelopes "
        "ADD COLUMN IF NOT EXISTS supersedes_envelope_id INTEGER "
        "REFERENCES signing_envelopes(id)"
    )
    op.execute(
        "ALTER TABLE signing_envelopes "
        "ADD COLUMN IF NOT EXISTS superseded_by_envelope_id INTEGER "
        "REFERENCES signing_envelopes(id)"
    )
    op.execute(
        "ALTER TABLE signing_envelopes "
        "DROP CONSTRAINT IF EXISTS ck_envelope_preparation_state"
    )
    op.create_check_constraint(
        "ck_envelope_preparation_state",
        "signing_envelopes",
        "state IN ('draft','prepared','cancelled','withdrawn','superseded')",
    )


def downgrade():
    op.drop_constraint(
        "ck_envelope_preparation_state", "signing_envelopes", type_="check"
    )
    op.create_check_constraint(
        "ck_envelope_preparation_state",
        "signing_envelopes",
        "state IN ('draft','prepared','cancelled','withdrawn')",
    )
    op.drop_column("signing_envelopes", "superseded_by_envelope_id")
    op.drop_column("signing_envelopes", "supersedes_envelope_id")
