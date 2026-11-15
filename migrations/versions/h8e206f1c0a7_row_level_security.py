"""Enable PostgreSQL row-level security on trust-critical tables.

Closes threat-model residual G2. The application-layer
``TenantScopedRepository`` already refuses unscoped queries; RLS is
defence in depth. Both have to agree on the active tenant for the
row to be returned.

How it works:

* ``trustseal_set_tenant(tenant_id)`` stores the active tenant on
  the Postgres session via ``SET LOCAL``. The Flask SQLAlchemy
  ``before_cursor_execute`` hook calls it once per transaction from
  the JWT identity.
* Every protected table enables RLS with a single ``USING`` policy
  that compares ``organization_id`` to the session variable. A
  session that never sets the variable sees zero rows — fail-closed.
* The policy is bypassed for superuser and for roles granted
  ``BYPASSRLS``; migration-time maintenance (Alembic, backup tooling)
  normally runs as a role with BYPASSRLS.

Revision ID: h8e206f1c0a7
Revises: g7d195e0b9f6
"""
from alembic import op
import sqlalchemy as sa

revision = "h8e206f1c0a7"
down_revision = "g7d195e0b9f6"
branch_labels = None
depends_on = None

PROTECTED_TABLES = [
    "documents",
    "signing_envelopes",
    "finalized_pdfs",
    "evidence_retentions",
    "validation_dossiers",
    "webhook_endpoints",
    "webhook_deliveries",
    "idempotency_records",
    "stamped_pdfs",
    "security_events",
    "audit_chain_anchors",
]


def upgrade():
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE OR REPLACE FUNCTION trustseal_current_tenant()
        RETURNS INTEGER AS $$
        BEGIN
            RETURN NULLIF(current_setting('trustseal.current_tenant_id', true), '')::INTEGER;
        EXCEPTION WHEN OTHERS THEN
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql STABLE;
        """
    )

    # Variant used by idempotency rows which carry ``tenant_id`` rather
    # than ``organization_id``.
    bind.exec_driver_sql(
        """
        CREATE OR REPLACE FUNCTION trustseal_tenant_match(target INTEGER)
        RETURNS BOOLEAN AS $$
        DECLARE active INTEGER;
        BEGIN
            active := trustseal_current_tenant();
            RETURN active IS NOT NULL AND target = active;
        END;
        $$ LANGUAGE plpgsql STABLE;
        """
    )

    for table in PROTECTED_TABLES:
        column = "tenant_id" if table == "idempotency_records" else "organization_id"
        bind.exec_driver_sql(
            f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'
        )
        bind.exec_driver_sql(
            f'DROP POLICY IF EXISTS trustseal_tenant_isolation ON "{table}"'
        )
        bind.exec_driver_sql(
            f"""
            CREATE POLICY trustseal_tenant_isolation
            ON "{table}"
            USING (trustseal_tenant_match({column}))
            WITH CHECK (trustseal_tenant_match({column}))
            """
        )


def downgrade():
    bind = op.get_bind()
    for table in PROTECTED_TABLES:
        bind.exec_driver_sql(
            f'DROP POLICY IF EXISTS trustseal_tenant_isolation ON "{table}"'
        )
        bind.exec_driver_sql(
            f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'
        )
    bind.exec_driver_sql("DROP FUNCTION IF EXISTS trustseal_tenant_match(INTEGER)")
    bind.exec_driver_sql("DROP FUNCTION IF EXISTS trustseal_current_tenant()")
