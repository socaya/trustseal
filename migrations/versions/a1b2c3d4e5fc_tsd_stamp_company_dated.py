"""Add company_dated to tsd_stamps.kind CHECK

Revision ID: a1b2c3d4e5fc
Revises: a1b2c3d4e5fb
Create Date: 2026-11-18 02:30:00.000000
"""
from alembic import op


revision = 'a1b2c3d4e5fc'
down_revision = 'a1b2c3d4e5fb'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('ck_tsd_stamp_kind', 'tsd_stamps', type_='check')
    op.create_check_constraint(
        'ck_tsd_stamp_kind', 'tsd_stamps',
        "kind IN ('seal','date','company_dated','rubber','custom')",
    )


def downgrade():
    op.drop_constraint('ck_tsd_stamp_kind', 'tsd_stamps', type_='check')
    op.create_check_constraint(
        'ck_tsd_stamp_kind', 'tsd_stamps',
        "kind IN ('seal','date','rubber','custom')",
    )
