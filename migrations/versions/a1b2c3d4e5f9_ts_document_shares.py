"""ts_document_shares (TSD share grants)

Revision ID: a1b2c3d4e5f9
Revises: a1b2c3d4e5f8
Create Date: 2026-11-18 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f9'
down_revision = 'a1b2c3d4e5f8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ts_document_shares',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tsd_id', sa.Integer(), sa.ForeignKey('ts_documents.id'), nullable=False),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('grantee_user_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('grantee_email', sa.String(length=255)),
        sa.Column('permission', sa.String(length=16), nullable=False, server_default='view'),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime()),
        sa.Column('revoked_at', sa.DateTime()),
        sa.CheckConstraint(
            "permission IN ('view','comment','edit')",
            name='ck_tsd_share_permission',
        ),
        sa.UniqueConstraint('tsd_id', 'grantee_user_id', name='uq_tsd_share_doc_user'),
    )
    op.create_index('ix_ts_document_shares_tsd_id', 'ts_document_shares', ['tsd_id'])
    op.create_index('ix_ts_document_shares_organization_id', 'ts_document_shares', ['organization_id'])
    op.create_index('ix_ts_document_shares_grantee_user_id', 'ts_document_shares', ['grantee_user_id'])
    op.create_index('ix_ts_document_shares_revoked_at', 'ts_document_shares', ['revoked_at'])


def downgrade():
    op.drop_table('ts_document_shares')
