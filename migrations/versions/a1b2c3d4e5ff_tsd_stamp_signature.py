"""Add 'signature' kind to tsd_stamps CHECK constraint

Signature stamps carry a signatory name + title + optional date +
image, with a horizontal signature line. Spec §8.2.

Revision ID: a1b2c3d4e5ff
Revises: a1b2c3d4e5fe
Create Date: 2026-11-18 23:30:00.000000
"""
from alembic import op


revision = "a1b2c3d4e5ff"
down_revision = "a1b2c3d4e5fe"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_tsd_stamp_kind", "tsd_stamps", type_="check")
    op.create_check_constraint(
        "ck_tsd_stamp_kind", "tsd_stamps",
        "kind IN ('seal','date','company_dated','company_rect','rubber',"
        "'signature','custom')",
    )


def downgrade():
    op.drop_constraint("ck_tsd_stamp_kind", "tsd_stamps", type_="check")
    op.create_check_constraint(
        "ck_tsd_stamp_kind", "tsd_stamps",
        "kind IN ('seal','date','company_dated','company_rect','rubber','custom')",
    )
