"""SignerAppearance: typed + uploaded kinds.

Revision ID: aa07g2a9b1c0
Revises: z6f195c8a0b9
"""
from alembic import op
import sqlalchemy as sa

revision = "aa07g2a9b1c0"
down_revision = "z6f195c8a0b9"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE signer_appearances "
        "ADD COLUMN IF NOT EXISTS appearance_kind VARCHAR(16) "
        "NOT NULL DEFAULT 'drawn'"
    )
    op.execute(
        "ALTER TABLE signer_appearances "
        "ADD COLUMN IF NOT EXISTS source_label VARCHAR(200)"
    )
    op.execute(
        "ALTER TABLE signer_appearances "
        "DROP CONSTRAINT IF EXISTS ck_signer_appearance_kind"
    )
    op.create_check_constraint(
        "ck_signer_appearance_kind",
        "signer_appearances",
        "appearance_kind IN ('drawn','typed','uploaded')",
    )


def downgrade():
    op.drop_constraint(
        "ck_signer_appearance_kind", "signer_appearances", type_="check"
    )
    op.drop_column("signer_appearances", "source_label")
    op.drop_column("signer_appearances", "appearance_kind")
