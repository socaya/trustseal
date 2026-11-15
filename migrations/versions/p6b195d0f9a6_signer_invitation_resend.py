"""Allow multiple signer_invitations per participant.

The original schema enforced a strict ``UNIQUE(envelope_id,
participant_id)`` which blocked the resend-invitation flow. Replace
it with a partial unique index that only applies to *active* rows
(``revoked_at IS NULL AND consumed_at IS NULL``). History rows
remain.

Revision ID: p6b195d0f9a6
Revises: o5a084c9e8f5
"""
from alembic import op
import sqlalchemy as sa

revision = "p6b195d0f9a6"
down_revision = "o5a084c9e8f5"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE signer_invitations "
        "DROP CONSTRAINT IF EXISTS uq_signer_invitation_participant"
    )
    op.execute(
        "DROP INDEX IF EXISTS uq_signer_invitation_participant_active"
    )
    op.create_index(
        "uq_signer_invitation_participant_active",
        "signer_invitations",
        ["envelope_id", "participant_id"],
        unique=True,
        postgresql_where=sa.text(
            "revoked_at IS NULL AND consumed_at IS NULL"
        ),
    )


def downgrade():
    op.drop_index(
        "uq_signer_invitation_participant_active",
        table_name="signer_invitations",
    )
    op.create_unique_constraint(
        "uq_signer_invitation_participant",
        "signer_invitations",
        ["envelope_id", "participant_id"],
    )
