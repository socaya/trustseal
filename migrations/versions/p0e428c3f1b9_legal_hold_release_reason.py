"""Attribute legal-hold release to a documented decision.

Revision ID: p0e428c3f1b9
Revises: o9d317b2e0a8
"""
from alembic import op
import sqlalchemy as sa

revision = "p0e428c3f1b9"
down_revision = "o9d317b2e0a8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "evidence_legal_holds",
        sa.Column("release_reason", sa.String(500), nullable=True),
    )
    op.execute("""
        ALTER TABLE evidence_legal_holds
        ADD CONSTRAINT ck_evidence_hold_release_reason
        CHECK (
          (released_at IS NULL AND release_reason IS NULL)
          OR (released_at IS NOT NULL AND length(btrim(release_reason)) >= 15)
        )
    """)
    op.execute("""
      CREATE OR REPLACE FUNCTION trustseal_legal_hold_release_only()
      RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP = 'DELETE' THEN
          RAISE EXCEPTION 'legal hold cannot be deleted';
        END IF;
        IF to_jsonb(NEW) - 'released_by_id' - 'released_at' - 'release_reason'
           IS DISTINCT FROM to_jsonb(OLD) - 'released_by_id' - 'released_at' - 'release_reason'
           OR OLD.released_at IS NOT NULL
           OR NEW.released_at IS NULL
           OR NEW.released_by_id IS NULL
           OR NEW.release_reason IS NULL
           OR length(btrim(NEW.release_reason)) < 15
           OR NEW.released_at < OLD.requested_at
           OR NEW.released_by_id = OLD.requested_by_id
        THEN
          RAISE EXCEPTION 'legal hold release requires an independent documented decision';
        END IF;
        RETURN NEW;
      END; $$;
    """)


def downgrade():
    raise RuntimeError("Legal-hold release provenance cannot be destructively downgraded")
