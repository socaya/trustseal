"""ts_documents (TrustSeal proprietary document)

Revision ID: a1b2c3d4e5f6
Revises: 1856829bd7b1
Create Date: 2026-11-17 19:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
# Merges the two parallel heads (1856829bd7b1 + kk07q2k9l1g0) into a
# single linear chain so ``flask db upgrade`` has an unambiguous target.
down_revision = ('1856829bd7b1', 'kk07q2k9l1g0')
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ts_documents',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(length=1000)),
        sa.Column('tags', sa.String(length=500)),
        sa.Column('export_policy', sa.String(length=24), nullable=False, server_default='pdf_allowed'),
        sa.Column('status', sa.String(length=24), nullable=False, server_default='draft'),
        sa.Column('ciphertext', sa.LargeBinary(), nullable=False),
        sa.Column('ciphertext_sha256', sa.String(length=64), nullable=False),
        sa.Column('plaintext_bytes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column(
            'content_mime', sa.String(length=80), nullable=False,
            server_default='application/vnd.trustseal.doc+json',
        ),
        sa.Column('version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime()),
        sa.CheckConstraint(
            "export_policy IN ('pdf_allowed','encrypted_only')",
            name='ck_tsd_export_policy',
        ),
        sa.CheckConstraint(
            "status IN ('draft','finalized','archived')",
            name='ck_tsd_status',
        ),
        sa.CheckConstraint('version > 0', name='ck_tsd_version_positive'),
    )
    op.create_index('ix_ts_documents_organization_id', 'ts_documents', ['organization_id'])
    op.create_index('ix_ts_documents_created_by_id', 'ts_documents', ['created_by_id'])
    op.create_index('ix_ts_documents_deleted_at', 'ts_documents', ['deleted_at'])


def downgrade():
    op.drop_index('ix_ts_documents_deleted_at', table_name='ts_documents')
    op.drop_index('ix_ts_documents_created_by_id', table_name='ts_documents')
    op.drop_index('ix_ts_documents_organization_id', table_name='ts_documents')
    op.drop_table('ts_documents')
