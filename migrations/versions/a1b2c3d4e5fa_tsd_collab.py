"""TSD collab tables: comments, external shares, approvals, presence

Revision ID: a1b2c3d4e5fa
Revises: a1b2c3d4e5f9
Create Date: 2026-11-18 01:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5fa'
down_revision = 'a1b2c3d4e5f9'
branch_labels = None
depends_on = None


def upgrade():
    # --- comments ---
    op.create_table(
        'ts_document_comments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tsd_id', sa.Integer(), sa.ForeignKey('ts_documents.id'), nullable=False),
        sa.Column('parent_comment_id', sa.Integer(), sa.ForeignKey('ts_document_comments.id')),
        sa.Column('author_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('anchor_id', sa.String(length=64)),
        sa.Column('anchor_text', sa.String(length=500)),
        sa.Column('resolved_at', sa.DateTime()),
        sa.Column('resolved_by_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_ts_document_comments_tsd_id', 'ts_document_comments', ['tsd_id'])
    op.create_index('ix_ts_document_comments_parent', 'ts_document_comments', ['parent_comment_id'])
    op.create_index('ix_ts_document_comments_resolved_at', 'ts_document_comments', ['resolved_at'])

    # --- external shares ---
    op.create_table(
        'ts_document_external_shares',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tsd_id', sa.Integer(), sa.ForeignKey('ts_documents.id'), nullable=False),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('recipient_email', sa.String(length=255), nullable=False),
        sa.Column('permission', sa.String(length=16), nullable=False, server_default='view'),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('revoked_at', sa.DateTime()),
        sa.Column('consumed_at', sa.DateTime()),
        sa.Column('access_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_access_at', sa.DateTime()),
        sa.CheckConstraint("permission IN ('view','comment')",
                           name='ck_tsd_external_share_permission'),
    )
    op.create_index('ix_ts_ext_share_tsd_id', 'ts_document_external_shares', ['tsd_id'])
    op.create_index('ix_ts_ext_share_org_id', 'ts_document_external_shares', ['organization_id'])
    op.create_index('ix_ts_ext_share_token_hash', 'ts_document_external_shares', ['token_hash'])
    op.create_index('ix_ts_ext_share_revoked_at', 'ts_document_external_shares', ['revoked_at'])

    # --- approvals ---
    op.create_table(
        'ts_document_approvals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tsd_id', sa.Integer(), sa.ForeignKey('ts_documents.id'), nullable=False),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('approver_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('order_index', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=24), nullable=False, server_default='pending'),
        sa.Column('note', sa.String(length=1000)),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('decided_at', sa.DateTime()),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected','changes_requested')",
            name='ck_tsd_approval_status',
        ),
        sa.UniqueConstraint('tsd_id', 'approver_id', name='uq_tsd_approval_doc_approver'),
    )
    op.create_index('ix_ts_approval_tsd_id', 'ts_document_approvals', ['tsd_id'])
    op.create_index('ix_ts_approval_org_id', 'ts_document_approvals', ['organization_id'])

    # --- presence ---
    op.create_table(
        'ts_document_presence',
        sa.Column('tsd_id', sa.Integer(), sa.ForeignKey('ts_documents.id'), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('last_ping_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_ts_presence_last_ping', 'ts_document_presence', ['last_ping_at'])


def downgrade():
    op.drop_table('ts_document_presence')
    op.drop_table('ts_document_approvals')
    op.drop_table('ts_document_external_shares')
    op.drop_table('ts_document_comments')
