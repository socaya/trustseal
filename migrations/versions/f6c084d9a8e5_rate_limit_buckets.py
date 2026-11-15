"""Durable fixed-window rate-limit counters.

Revision ID: f6c084d9a8e5
Revises: e5b973c8f7d4
"""
from alembic import op
import sqlalchemy as sa

revision = "f6c084d9a8e5"
down_revision = "e5b973c8f7d4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rate_limit_buckets",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False, start=1, cycle=False),
            primary_key=True,
        ),
        sa.Column("bucket_key", sa.String(160), nullable=False),
        sa.Column("window_start", sa.DateTime(), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "bucket_key", "window_start",
            name="uq_rate_limit_bucket_key_window",
        ),
        sa.CheckConstraint("hits >= 0", name="ck_rate_limit_hits_nonneg"),
        sa.CheckConstraint(
            "window_seconds > 0", name="ck_rate_limit_window_positive"
        ),
    )
    op.create_index(
        "ix_rate_limit_buckets_window_start",
        "rate_limit_buckets",
        ["window_start"],
    )


def downgrade():
    op.drop_index(
        "ix_rate_limit_buckets_window_start",
        table_name="rate_limit_buckets",
    )
    op.drop_table("rate_limit_buckets")
