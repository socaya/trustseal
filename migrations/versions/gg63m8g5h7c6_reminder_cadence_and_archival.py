"""Per-envelope reminder cadence + archival (Phase R1 + R2).

Revision ID: gg63m8g5h7c6
Revises: ff52l7f4g6b5
"""
from alembic import op
import sqlalchemy as sa

revision = "gg63m8g5h7c6"
down_revision = "ff52l7f4g6b5"
branch_labels = None
depends_on = None


def upgrade():
    # R1 — per-envelope reminder cadence overrides.
    op.add_column(
        "signing_envelopes",
        sa.Column("reminder_cooloff_hours", sa.Integer, nullable=True),
    )
    op.add_column(
        "signing_envelopes",
        sa.Column("reminder_max_count", sa.Integer, nullable=True),
    )
    op.create_check_constraint(
        "ck_envelope_reminder_cooloff_range",
        "signing_envelopes",
        "reminder_cooloff_hours IS NULL OR reminder_cooloff_hours BETWEEN 1 AND 720",
    )
    op.create_check_constraint(
        "ck_envelope_reminder_max_count_range",
        "signing_envelopes",
        "reminder_max_count IS NULL OR reminder_max_count BETWEEN 1 AND 50",
    )

    # R1 — running tally of reminders per invitation.
    op.add_column(
        "signer_invitations",
        sa.Column(
            "reminder_count",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
    )

    # R2 — archival columns.
    op.add_column(
        "signing_envelopes",
        sa.Column("archived_at", sa.DateTime, nullable=True),
    )
    op.add_column(
        "signing_envelopes",
        sa.Column(
            "archived_by_id",
            sa.Integer,
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_signing_envelopes_archived_at",
        "signing_envelopes",
        ["archived_at"],
    )


def downgrade():
    op.drop_index(
        "ix_signing_envelopes_archived_at",
        table_name="signing_envelopes",
    )
    op.drop_column("signing_envelopes", "archived_by_id")
    op.drop_column("signing_envelopes", "archived_at")
    op.drop_column("signer_invitations", "reminder_count")
    op.drop_constraint(
        "ck_envelope_reminder_max_count_range",
        "signing_envelopes",
        type_="check",
    )
    op.drop_constraint(
        "ck_envelope_reminder_cooloff_range",
        "signing_envelopes",
        type_="check",
    )
    op.drop_column("signing_envelopes", "reminder_max_count")
    op.drop_column("signing_envelopes", "reminder_cooloff_hours")
