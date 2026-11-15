"""Per-participant signing fields.

Revision ID: n4f973b8d7e4
Revises: m3e862a7c6d3
"""
from alembic import op
import sqlalchemy as sa

revision = "n4f973b8d7e4"
down_revision = "m3e862a7c6d3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "envelope_fields",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "envelope_id",
            sa.Integer(),
            sa.ForeignKey("signing_envelopes.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "participant_id",
            sa.Integer(),
            sa.ForeignKey("envelope_participants.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("field_type", sa.String(20), nullable=False),
        sa.Column("label", sa.String(100), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("x_pt", sa.Numeric(10, 3), nullable=False),
        sa.Column("y_pt", sa.Numeric(10, 3), nullable=False),
        sa.Column("width_pt", sa.Numeric(10, 3), nullable=False),
        sa.Column("height_pt", sa.Numeric(10, 3), nullable=False),
        sa.Column(
            "required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "field_type IN ('signature','initials','date','text','checkbox')",
            name="ck_envelope_field_type",
        ),
        sa.CheckConstraint(
            "page_number > 0", name="ck_envelope_field_page"
        ),
        sa.CheckConstraint(
            "width_pt > 0 AND height_pt > 0",
            name="ck_envelope_field_rect",
        ),
    )


def downgrade():
    op.drop_table("envelope_fields")
