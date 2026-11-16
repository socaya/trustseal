"""Document template publication workflow + version history.

Revision ID: r8d317f2b1c8
Revises: q7c206e1a0b7

Adds state machine columns + a new ``document_template_versions``
table. Backward-compatible: existing rows keep working with
``state='draft'``.
"""
from alembic import op
import sqlalchemy as sa

revision = "r8d317f2b1c8"
down_revision = "q7c206e1a0b7"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE document_templates "
        "ADD COLUMN IF NOT EXISTS organization_id INTEGER "
        "REFERENCES organizations(id)"
    )
    op.execute(
        "ALTER TABLE document_templates "
        "ADD COLUMN IF NOT EXISTS state VARCHAR(20) "
        "NOT NULL DEFAULT 'draft'"
    )
    op.execute(
        "ALTER TABLE document_templates "
        "ADD COLUMN IF NOT EXISTS current_version_id BIGINT"
    )
    op.execute(
        "ALTER TABLE document_templates "
        "ADD COLUMN IF NOT EXISTS published_at TIMESTAMP"
    )
    op.execute(
        "ALTER TABLE document_templates "
        "ADD COLUMN IF NOT EXISTS published_by_id INTEGER "
        "REFERENCES users(id)"
    )
    op.execute(
        "ALTER TABLE document_templates "
        "ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP"
    )
    op.execute(
        "ALTER TABLE document_templates "
        "ADD COLUMN IF NOT EXISTS archived_by_id INTEGER "
        "REFERENCES users(id)"
    )
    op.execute(
        "ALTER TABLE document_templates "
        "DROP CONSTRAINT IF EXISTS ck_document_template_state"
    )
    op.create_check_constraint(
        "ck_document_template_state",
        "document_templates",
        "state IN ('draft','published','archived')",
    )
    op.create_table(
        "document_template_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "template_id",
            sa.Integer(),
            sa.ForeignKey("document_templates.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column(
            "published_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "template_id", "revision",
            name="uq_document_template_version",
        ),
        sa.CheckConstraint(
            "revision > 0", name="ck_document_template_version_revision",
        ),
    )
    # Now that the table exists, add the FK that points at it.
    op.execute(
        "ALTER TABLE document_templates "
        "DROP CONSTRAINT IF EXISTS fk_document_templates_current_version"
    )
    op.execute(
        "ALTER TABLE document_templates "
        "ADD CONSTRAINT fk_document_templates_current_version "
        "FOREIGN KEY (current_version_id) "
        "REFERENCES document_template_versions(id)"
    )


def downgrade():
    op.execute(
        "ALTER TABLE document_templates "
        "DROP CONSTRAINT IF EXISTS fk_document_templates_current_version"
    )
    op.drop_table("document_template_versions")
    op.drop_constraint(
        "ck_document_template_state", "document_templates", type_="check"
    )
    op.drop_column("document_templates", "archived_by_id")
    op.drop_column("document_templates", "archived_at")
    op.drop_column("document_templates", "published_by_id")
    op.drop_column("document_templates", "published_at")
    op.drop_column("document_templates", "current_version_id")
    op.drop_column("document_templates", "state")
    op.drop_column("document_templates", "organization_id")
