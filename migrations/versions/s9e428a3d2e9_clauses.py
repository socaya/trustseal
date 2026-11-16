"""Clause library tables.

Revision ID: s9e428a3d2e9
Revises: r8d317f2b1c8
"""
from alembic import op
import sqlalchemy as sa

revision = "s9e428a3d2e9"
down_revision = "r8d317f2b1c8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "clauses",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(80), nullable=True),
        sa.Column("state", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("current_version_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column(
            "approved_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column(
            "archived_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "state IN ('draft','approved','archived')", name="ck_clause_state"
        ),
        sa.UniqueConstraint(
            "organization_id", "name", name="uq_clause_org_name"
        ),
    )
    op.create_table(
        "clause_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "clause_id",
            sa.Integer(),
            sa.ForeignKey("clauses.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column(
            "approved_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "clause_id", "revision", name="uq_clause_version"
        ),
        sa.CheckConstraint(
            "revision > 0", name="ck_clause_version_revision"
        ),
    )
    op.execute(
        "ALTER TABLE clauses "
        "ADD CONSTRAINT fk_clauses_current_version "
        "FOREIGN KEY (current_version_id) REFERENCES clause_versions(id)"
    )


def downgrade():
    op.execute(
        "ALTER TABLE clauses DROP CONSTRAINT IF EXISTS fk_clauses_current_version"
    )
    op.drop_table("clause_versions")
    op.drop_table("clauses")
