"""Add company_rect kind to tsd_stamps CHECK constraint

Rectangular Company stamps carry a header + multi-line address + reg
number + contact lines + optional date. Separate from the round
``seal`` / ``company_dated`` kinds and from the short-text ``rubber``
kind which is centred-word-oriented.

Revision ID: a1b2c3d4e5fe
Revises: a1b2c3d4e5fd
Create Date: 2026-11-18 18:00:00.000000
"""
from alembic import op


revision = "a1b2c3d4e5fe"
down_revision = "a1b2c3d4e5fd"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_tsd_stamp_kind", "tsd_stamps", type_="check")
    op.create_check_constraint(
        "ck_tsd_stamp_kind", "tsd_stamps",
        "kind IN ('seal','date','company_dated','company_rect','rubber','custom')",
    )


def downgrade():
    op.drop_constraint("ck_tsd_stamp_kind", "tsd_stamps", type_="check")
    op.create_check_constraint(
        "ck_tsd_stamp_kind", "tsd_stamps",
        "kind IN ('seal','date','company_dated','rubber','custom')",
    )
