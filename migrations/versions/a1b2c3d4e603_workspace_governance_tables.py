"""Create workspace governance, media, letterhead, and contract workflow tables.

Revision ID: a1b2c3d4e603
Revises: a1b2c3d4e602
Create Date: 2026-11-24
"""
from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e603"
down_revision = "a1b2c3d4e602"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade():
    if not _table_exists("contract_workflows"):
        op.create_table(
            "contract_workflows",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("ts_documents.id"), nullable=False, unique=True),
            sa.Column("stage", sa.String(length=24), nullable=False, server_default="draft"),
            sa.Column("counterparty_name", sa.String(length=200), nullable=True),
            sa.Column("deal_value", sa.String(length=64), nullable=True),
            sa.Column("currency", sa.String(length=12), nullable=False, server_default="USD"),
            sa.Column("effective_date", sa.String(length=32), nullable=True),
            sa.Column("governing_law", sa.String(length=120), nullable=True),
            sa.Column("letterhead_id", sa.Integer(), nullable=True),
            sa.Column("stamp_id", sa.Integer(), nullable=True),
            sa.Column("checklist_json", sa.JSON(), nullable=False),
            sa.Column("signers_json", sa.JSON(), nullable=False),
            sa.Column("events_json", sa.JSON(), nullable=False),
            sa.Column("closed_at", sa.DateTime(), nullable=True),
            sa.Column("execution_sha256", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_contract_workflows_organization_id", "contract_workflows", ["organization_id"])
        op.create_index("ix_contract_workflows_document_id", "contract_workflows", ["document_id"], unique=True)

    if not _table_exists("tsd_media_assets"):
        op.create_table(
            "tsd_media_assets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name", sa.String(length=140), nullable=False),
            sa.Column("category", sa.String(length=24), nullable=False, server_default="logo"),
            sa.Column("mime_type", sa.String(length=64), nullable=False, server_default="image/png"),
            sa.Column("data_uri", sa.Text(), nullable=False),
            sa.Column("width", sa.Integer(), nullable=True),
            sa.Column("height", sa.Integer(), nullable=True),
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_tsd_media_assets_organization_id", "tsd_media_assets", ["organization_id"])
        op.create_index("ix_tsd_media_assets_category", "tsd_media_assets", ["category"])
        op.create_index("ix_tsd_media_assets_sha256", "tsd_media_assets", ["sha256"])
        op.create_index("ix_tsd_media_assets_deleted_at", "tsd_media_assets", ["deleted_at"])

    if not _table_exists("tsd_letterheads"):
        op.create_table(
            "tsd_letterheads",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name", sa.String(length=140), nullable=False),
            sa.Column("description", sa.String(length=300), nullable=True),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("layout", sa.JSON(), nullable=False),
            sa.Column("header_html", sa.Text(), nullable=False, server_default=""),
            sa.Column("footer_html", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_tsd_letterheads_organization_id", "tsd_letterheads", ["organization_id"])
        op.create_index("ix_tsd_letterheads_deleted_at", "tsd_letterheads", ["deleted_at"])

    if not _table_exists("signature_approval_states"):
        op.create_table(
            "signature_approval_states",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column(
                "signature_profile_id",
                sa.Integer(),
                sa.ForeignKey("signature_profiles.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
            ),
            sa.Column("approval_status", sa.String(length=24), nullable=False, server_default="pending"),
            sa.Column("capture_engine", sa.String(length=40), nullable=False, server_default="ts_hq_engine"),
            sa.Column("device_name", sa.String(length=120), nullable=True),
            sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_signature_approval_states_organization_id", "signature_approval_states", ["organization_id"])
        op.create_index(
            "ix_signature_approval_states_signature_profile_id",
            "signature_approval_states",
            ["signature_profile_id"],
            unique=True,
        )

    if not _table_exists("signature_usage_logs"):
        op.create_table(
            "signature_usage_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column(
                "signature_profile_id",
                sa.Integer(),
                sa.ForeignKey("signature_profiles.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("requester_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("document_id", sa.Integer(), nullable=True),
            sa.Column("document_title", sa.String(length=240), nullable=True),
            sa.Column("otp_code_hash", sa.String(length=64), nullable=False),
            sa.Column("otp_last2", sa.String(length=4), nullable=True),
            sa.Column("otp_expires_at", sa.DateTime(), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="otp_pending"),
            sa.Column("ip_address", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("applied_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_signature_usage_logs_organization_id", "signature_usage_logs", ["organization_id"])
        op.create_index("ix_signature_usage_logs_signature_profile_id", "signature_usage_logs", ["signature_profile_id"])
        op.create_index("ix_signature_usage_logs_owner_user_id", "signature_usage_logs", ["owner_user_id"])
        op.create_index("ix_signature_usage_logs_requester_user_id", "signature_usage_logs", ["requester_user_id"])
        op.create_index("ix_signature_usage_logs_document_id", "signature_usage_logs", ["document_id"])


def downgrade():
    for name in (
        "signature_usage_logs",
        "signature_approval_states",
        "tsd_letterheads",
        "tsd_media_assets",
        "contract_workflows",
    ):
        if _table_exists(name):
            op.drop_table(name)
