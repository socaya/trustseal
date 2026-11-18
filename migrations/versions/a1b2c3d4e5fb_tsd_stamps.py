"""tsd_stamps (tenant-owned SVG stamp designs)

Revision ID: a1b2c3d4e5fb
Revises: a1b2c3d4e5fa
Create Date: 2026-11-18 02:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5fb'
down_revision = 'a1b2c3d4e5fa'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tsd_stamps',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False, server_default='seal'),
        sa.Column('layout', sa.JSON(), nullable=False),
        sa.Column('svg', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime()),
        sa.CheckConstraint("kind IN ('seal','date','rubber','custom')",
                           name='ck_tsd_stamp_kind'),
        sa.UniqueConstraint('organization_id', 'name', name='uq_tsd_stamp_org_name'),
    )
    op.create_index('ix_tsd_stamps_organization_id', 'tsd_stamps', ['organization_id'])
    op.create_index('ix_tsd_stamps_deleted_at', 'tsd_stamps', ['deleted_at'])


def downgrade():
    op.drop_table('tsd_stamps')
