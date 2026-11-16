"""SP-signing credentials for SAML AuthnRequests.

Revision ID: z6f195c8a0b9
Revises: y5e084f7a9c8
"""
from alembic import op
import sqlalchemy as sa

revision = "z6f195c8a0b9"
down_revision = "y5e084f7a9c8"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE saml_providers "
        "ADD COLUMN IF NOT EXISTS sp_signing_private_key_pem TEXT"
    )
    op.execute(
        "ALTER TABLE saml_providers "
        "ADD COLUMN IF NOT EXISTS sp_signing_cert_pem TEXT"
    )


def downgrade():
    op.drop_column("saml_providers", "sp_signing_cert_pem")
    op.drop_column("saml_providers", "sp_signing_private_key_pem")
