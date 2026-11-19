"""tsd_stamp_insertions — signed receipts for stamp insertion into TSDs

Each row is the signed, server-side record that a given stamp was
inserted into a given document (or context) at a given time by a
given user. The inserted SVG carries a lightweight ``receipt-id``
back-reference so the TSD editor's verifier can validate authenticity
against this table.

Revision ID: a1b2c3d4e5fd
Revises: a1b2c3d4e5fc
Create Date: 2026-11-18 03:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5fd"
down_revision = "a1b2c3d4e5fc"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tsd_stamp_insertions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(),
                  sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("stamp_id", sa.Integer(),
                  sa.ForeignKey("tsd_stamps.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("document_id", sa.Integer(),
                  sa.ForeignKey("ts_documents.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("placed_by_id", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("placed_at", sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("context_label", sa.String(length=200), nullable=True),
        sa.Column("context_hash", sa.String(length=64), nullable=False),
        sa.Column("nonce",        sa.String(length=32), nullable=False),
        sa.Column("hmac_hex",     sa.String(length=64), nullable=False),
        sa.Column("key_version",  sa.Integer(), nullable=False,
                  server_default="1"),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_reason", sa.String(length=200), nullable=True),
        sa.UniqueConstraint("stamp_id", "nonce",
                            name="uq_tsd_stamp_insertion_nonce"),
    )
    op.create_index("ix_tsd_stamp_insertions_org",
                    "tsd_stamp_insertions", ["organization_id"])
    op.create_index("ix_tsd_stamp_insertions_stamp",
                    "tsd_stamp_insertions", ["stamp_id"])
    op.create_index("ix_tsd_stamp_insertions_doc",
                    "tsd_stamp_insertions", ["document_id"])
    op.create_index("ix_tsd_stamp_insertions_placed_at",
                    "tsd_stamp_insertions", ["placed_at"])


def downgrade():
    op.drop_table("tsd_stamp_insertions")
