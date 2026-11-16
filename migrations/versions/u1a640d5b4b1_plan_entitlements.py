"""Per-plan metered entitlements.

Revision ID: u1a640d5b4b1
Revises: t0f539c4a3f0
"""
from alembic import op
import sqlalchemy as sa

revision = "u1a640d5b4b1"
down_revision = "t0f539c4a3f0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "plan_entitlements",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "plan_id",
            sa.Integer(),
            sa.ForeignKey("subscription_plans.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("meter", sa.String(60), nullable=False),
        sa.Column("period", sa.String(20), nullable=False),
        sa.Column("hit_limit", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "plan_id", "meter", "period", name="uq_plan_entitlement"
        ),
        sa.CheckConstraint("hit_limit > 0", name="ck_plan_entitlement_limit"),
        sa.CheckConstraint(
            "period IN ('day','month','year')",
            name="ck_plan_entitlement_period",
        ),
    )


def downgrade():
    op.drop_table("plan_entitlements")
