"""tenant_keys (per-tenant DEK envelope storage)

Revision ID: a1b2c3d4e5f7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-17 20:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tenant_keys',
        sa.Column(
            'organization_id', sa.Integer(),
            sa.ForeignKey('organizations.id'), primary_key=True,
        ),
        sa.Column('wrapped_key', sa.LargeBinary(), nullable=False),
        sa.Column('master_key_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('tenant_key_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('rotated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table('tenant_keys')
