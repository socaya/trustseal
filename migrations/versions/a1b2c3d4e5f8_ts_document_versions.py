"""ts_document_versions (append-only TSD version snapshots)

Revision ID: a1b2c3d4e5f8
Revises: a1b2c3d4e5f7
Create Date: 2026-11-17 21:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f8'
down_revision = 'a1b2c3d4e5f7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ts_document_versions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tsd_id', sa.Integer(), sa.ForeignKey('ts_documents.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('ciphertext', sa.LargeBinary(), nullable=False),
        sa.Column('ciphertext_sha256', sa.String(length=64), nullable=False),
        sa.Column('plaintext_bytes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('change_note', sa.String(length=500)),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('tsd_id', 'version', name='uq_tsd_version'),
    )
    op.create_index('ix_ts_document_versions_tsd_id', 'ts_document_versions', ['tsd_id'])


def downgrade():
    op.drop_index('ix_ts_document_versions_tsd_id', table_name='ts_document_versions')
    op.drop_table('ts_document_versions')
