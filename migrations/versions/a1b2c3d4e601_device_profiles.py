"""Device profiles (§5 + §15) — manufacturer / model / imprint-area capabilities

A ``DeviceProfile`` row describes a physical stamp mechanism (e.g.,
Trodat Printy 4913 self-inking, 58x22 mm imprint, 1 colour). Stamps
can be optionally linked to a device so validation can warn when a
design exceeds the device's imprint area, uses too many colours, or
targets an incompatible shape.

Revision ID: a1b2c3d4e601
Revises: a1b2c3d4e600
Create Date: 2026-11-19 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e601"
down_revision = "a1b2c3d4e600"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "device_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=80), nullable=False, unique=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("manufacturer", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("mechanism", sa.String(length=32), nullable=False),
        sa.Column("imprint_w_mm", sa.Numeric(6, 2), nullable=False),
        sa.Column("imprint_h_mm", sa.Numeric(6, 2), nullable=False),
        sa.Column("shape_hint", sa.String(length=16), nullable=False,
                  server_default="rect"),
        sa.Column("supported_shapes", sa.JSON(), nullable=False),
        sa.Column("supported_colors", sa.JSON(), nullable=False),
        sa.Column("max_colors", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("min_stroke_mm", sa.Numeric(4, 2), nullable=False,
                  server_default="0.30"),
        sa.Column("has_date_band", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint(
            "mechanism IN ('self_inking','rubber','pre_inked','embossed','wax','digital')",
            name="ck_device_mechanism",
        ),
    )
    op.create_index("ix_device_profiles_mechanism",
                    "device_profiles", ["mechanism"])

    # Optional device link on stamp designs.
    op.add_column(
        "tsd_stamps",
        sa.Column("device_profile_id", sa.Integer(),
                  sa.ForeignKey("device_profiles.id"), nullable=True),
    )


def downgrade():
    op.drop_column("tsd_stamps", "device_profile_id")
    op.drop_index("ix_device_profiles_mechanism", table_name="device_profiles")
    op.drop_table("device_profiles")
