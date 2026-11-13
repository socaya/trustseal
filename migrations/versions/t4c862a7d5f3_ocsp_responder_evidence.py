"""Retain exact delegated OCSP responder certificate for independent replay.

Revision ID: t4c862a7d5f3
Revises: s3b751f6c4e2
"""
from alembic import op
import sqlalchemy as sa

revision = "t4c862a7d5f3"
down_revision = "s3b751f6c4e2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ocsp_evidence", sa.Column("responder_certificate_sha256", sa.String(64)))
    op.add_column("ocsp_evidence", sa.Column("responder_der_b64", sa.Text()))
    op.execute("""
        ALTER TABLE ocsp_evidence ADD CONSTRAINT ck_ocsp_responder_evidence_pair
        CHECK ((responder_certificate_sha256 IS NULL AND responder_der_b64 IS NULL)
            OR (responder_certificate_sha256 IS NOT NULL AND responder_der_b64 IS NOT NULL))
    """)


def downgrade():
    raise RuntimeError("Retained OCSP responder certificate history may not be deleted")
