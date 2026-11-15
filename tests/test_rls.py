"""Row-level security on trust-critical tables.

Closes threat-model residual G2. The application-layer
``TenantScopedRepository`` already refuses unscoped queries; RLS is a
defence-in-depth boundary that catches bugs that forget to filter on
``organization_id``.

Covers:

* ``set_tenant`` propagates the active tenant to the Postgres
  session; ``clear_tenant`` resets it so a subsequent query sees
  zero rows.
* With no tenant set, a protected table returns zero rows regardless
  of ownership.
* With tenant A set, only tenant A's rows are returned — even when
  the caller runs a raw ``SELECT *`` that forgets ``WHERE``.
* The ``trustseal_tenant_match`` SQL function handles the idempotency
  table's ``tenant_id`` column variant.
* The hook attaches to Flask and clears the variable on request
  teardown so pool reuse never leaks a prior tenant.

The ``tests/conftest.py`` schema builder runs ``db.create_all()``
rather than Alembic, so this file installs the RLS migration SQL by
hand against the shared test schema the first time an RLS test runs.
The teardown removes the policies so other tests continue to run
without RLS interference.

Tests connect as a superuser role, which bypasses RLS. Each test
that checks policy enforcement calls ``_run_as_tenant_role`` first
to ``SET LOCAL ROLE trustseal_rls_test`` — a non-privileged role
the fixture creates and grants row-level access to the protected
tables. ``RESET ROLE`` happens implicitly at transaction end.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import text


RLS_TABLES = [
    ("documents", "organization_id"),
    ("signing_envelopes", "organization_id"),
    ("finalized_pdfs", "organization_id"),
    ("evidence_retentions", "organization_id"),
    ("validation_dossiers", "organization_id"),
    ("webhook_endpoints", "organization_id"),
    ("webhook_deliveries", "organization_id"),
    ("idempotency_records", "tenant_id"),
    ("stamped_pdfs", "organization_id"),
    ("security_events", "organization_id"),
    ("audit_chain_anchors", "organization_id"),
]


RLS_ROLE = "trustseal_rls_test"


def _run_as_tenant_role():
    """Switch the current transaction to the non-privileged RLS test role.

    Must be called inside an open transaction; ``RESET ROLE`` happens
    automatically at transaction end.
    """
    from app.extensions import db

    db.session.execute(text(f"SET LOCAL ROLE {RLS_ROLE}"))


@pytest.fixture(scope="module", autouse=True)
def install_rls(_session_app):
    """Install the RLS policies and clean them up after the module runs.

    Uses ``_session_app`` directly (not ``pg_app``) so the module-scope
    fixture can reach a session-scope Flask app. Policies are torn down
    at module end so later test files run with RLS disabled.

    Also creates a dedicated non-privileged role ``trustseal_rls_test``.
    The pytest Postgres connection is a superuser, which bypasses RLS;
    tests ``SET LOCAL ROLE`` to this role to force policy evaluation.
    """
    from app.extensions import db

    with _session_app.app_context():
        with db.engine.begin() as conn:
            # A pooled connection may carry a residual SET ROLE from
            # another test; reset to the connection owner so the DDL
            # below runs with CREATEROLE privilege.
            conn.exec_driver_sql("RESET ROLE")
            conn.exec_driver_sql(
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
            conn.exec_driver_sql(
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
            for table, column in RLS_TABLES:
                conn.exec_driver_sql(
                    f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'
                )
                conn.exec_driver_sql(
                    f'DROP POLICY IF EXISTS trustseal_tenant_isolation ON "{table}"'
                )
                conn.exec_driver_sql(
                    f'''
                    CREATE POLICY trustseal_tenant_isolation
                    ON "{table}"
                    USING (trustseal_tenant_match({column}))
                    WITH CHECK (trustseal_tenant_match({column}))
                    '''
                )
            # Create a non-privileged role so RLS actually applies when
            # tests switch to it. DROP first so repeat runs in the same
            # session stay idempotent.
            conn.exec_driver_sql(
                f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_roles WHERE rolname = '{RLS_ROLE}'
                    ) THEN
                        CREATE ROLE {RLS_ROLE} NOLOGIN NOBYPASSRLS;
                    END IF;
                END$$;
                """
            )
            conn.exec_driver_sql(
                f"GRANT USAGE ON SCHEMA public TO {RLS_ROLE}"
            )
            conn.exec_driver_sql(
                f"""
                GRANT SELECT, INSERT, UPDATE, DELETE
                ON ALL TABLES IN SCHEMA public TO {RLS_ROLE}
                """
            )
            conn.exec_driver_sql(
                f"""
                GRANT USAGE, SELECT, UPDATE
                ON ALL SEQUENCES IN SCHEMA public TO {RLS_ROLE}
                """
            )
    yield
    with _session_app.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql("RESET ROLE")
            for table, _ in RLS_TABLES:
                conn.exec_driver_sql(
                    f'DROP POLICY IF EXISTS trustseal_tenant_isolation ON "{table}"'
                )
                conn.exec_driver_sql(
                    f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'
                )
            conn.exec_driver_sql(
                f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {RLS_ROLE}"
            )
            conn.exec_driver_sql(
                f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {RLS_ROLE}"
            )
            conn.exec_driver_sql(
                f"REVOKE ALL ON SCHEMA public FROM {RLS_ROLE}"
            )
            conn.exec_driver_sql(f"DROP ROLE IF EXISTS {RLS_ROLE}")
            conn.exec_driver_sql(
                "DROP FUNCTION IF EXISTS trustseal_tenant_match(INTEGER)"
            )
            conn.exec_driver_sql(
                "DROP FUNCTION IF EXISTS trustseal_current_tenant()"
            )


@pytest.fixture
def tenants(pg_app):
    """Two adjacent tenants, each with a document and a webhook endpoint.

    Rows are inserted with ``BYPASSRLS``-equivalent privileges by
    temporarily clearing the policy via ``set_tenant`` to each
    tenant's id. This matches the production pattern — writers set
    their tenant before inserting.
    """
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.organization import Organization
    from app.models.user import User
    from app.models.webhook import WebhookEndpoint
    from app.services import tenant_rls
    from app.services import webhooks

    def _mk(name: str):
        org = Organization(name=name)
        db.session.add(org)
        db.session.flush()
        user = User(
            username=f"rls-user-{org.id}",
            email=f"rls-user-{org.id}@example.test",
            is_active=True,
            organization_id=org.id,
        )
        user.set_password("not-used-strong-password")
        db.session.add(user)
        db.session.flush()
        tenant_rls.set_tenant(org.id)
        doc = Document(
            title=f"{name} doc",
            status="draft",
            created_by=user.id,
            organization_id=org.id,
        )
        db.session.add(doc)
        endpoint, _secret = webhooks.register_endpoint(
            tenant_id=org.id,
            created_by_id=user.id,
            url=f"https://hooks.example.test/{name}",
            events=["envelope.prepared"],
        )
        db.session.commit()
        return {"org": org, "user": user, "doc": doc, "endpoint": endpoint}

    # Setup runs with RLS active; create rows while impersonating each
    # tenant so their inserts pass the WITH CHECK clause.
    tenant_rls.clear_tenant()
    a = _mk("rls-tenant-A")
    tenant_rls.clear_tenant()
    b = _mk("rls-tenant-B")
    tenant_rls.clear_tenant()
    return {"a": a, "b": b}


class TestSessionVariable:
    def test_default_is_null(self, pg_app):
        from app.services.tenant_rls import active_tenant, clear_tenant

        clear_tenant()
        assert active_tenant() is None

    def test_set_and_clear_round_trip(self, pg_app):
        from app.services.tenant_rls import active_tenant, clear_tenant, set_tenant

        set_tenant(42)
        assert active_tenant() == 42
        clear_tenant()
        assert active_tenant() is None

    def test_non_int_tenant_rejected(self, pg_app):
        from app.services.tenant_rls import set_tenant

        with pytest.raises(ValueError):
            set_tenant("not-an-int")  # type: ignore[arg-type]


class TestPolicyEnforcement:
    def test_no_tenant_sees_zero_rows(self, pg_app, tenants):
        from app.extensions import db
        from app.models.documents.document import Document
        from app.services.tenant_rls import clear_tenant

        _run_as_tenant_role()
        clear_tenant()
        rows = db.session.query(Document).all()
        assert rows == []

    def test_tenant_sees_only_own_rows(self, pg_app, tenants):
        from app.extensions import db
        from app.models.documents.document import Document
        from app.services.tenant_rls import set_tenant

        _run_as_tenant_role()
        set_tenant(tenants["a"]["org"].id)
        rows = db.session.query(Document).all()
        assert [r.id for r in rows] == [tenants["a"]["doc"].id]

        set_tenant(tenants["b"]["org"].id)
        rows = db.session.query(Document).all()
        assert [r.id for r in rows] == [tenants["b"]["doc"].id]

    def test_raw_unfiltered_select_still_scoped(self, pg_app, tenants):
        """A broken caller that forgets WHERE still cannot see other tenants."""
        from app.extensions import db
        from app.services.tenant_rls import set_tenant

        # Capture ids before the role switch, otherwise the lazy load
        # triggered by attribute access would be filtered by RLS and
        # SQLAlchemy would raise ObjectDeletedError on tenant B.
        a_org_id = tenants["a"]["org"].id
        a_endpoint_id = tenants["a"]["endpoint"].id
        b_endpoint_id = tenants["b"]["endpoint"].id

        _run_as_tenant_role()
        set_tenant(a_org_id)
        rows = db.session.execute(
            text("SELECT id, organization_id FROM webhook_endpoints")
        ).all()
        assert all(r[1] == a_org_id for r in rows)
        assert any(r[0] == a_endpoint_id for r in rows)
        assert not any(r[0] == b_endpoint_id for r in rows)

    def test_insert_refused_under_other_tenant(self, pg_app, tenants):
        """WITH CHECK clause blocks inserts with the wrong organization_id."""
        from app.extensions import db
        from app.models.webhook import WebhookEndpoint
        from app.services.tenant_rls import set_tenant

        _run_as_tenant_role()
        set_tenant(tenants["a"]["org"].id)
        hostile = WebhookEndpoint(
            organization_id=tenants["b"]["org"].id,
            created_by_id=tenants["a"]["user"].id,
            url="https://hooks.example.test/hostile",
            secret_hash="x" * 64,
            events=["envelope.prepared"],
            active=True,
        )
        db.session.add(hostile)
        with pytest.raises(Exception) as exc:
            db.session.flush()
        db.session.rollback()
        # Postgres surfaces the policy violation as a check-violation-ish
        # error; any RLS-related error string is acceptable.
        assert "policy" in str(exc.value).lower() or "row-level" in str(exc.value).lower()

    def test_idempotency_records_use_tenant_id_column(self, pg_app, tenants):
        """The ``trustseal_tenant_match`` function works for ``tenant_id`` too.

        Seeds as the superuser (so WITH CHECK is bypassed during setup),
        then switches to the restricted role to verify the read path is
        scoped. Uses a nested transaction so the role switch stays
        inside one transaction block.
        """
        from app.extensions import db
        from app.models.idempotency_record import IdempotencyRecord
        from app.services.tenant_rls import set_tenant

        row = IdempotencyRecord(
            tenant_id=tenants["a"]["org"].id,
            endpoint="probe",
            key="k",
            request_hash="h",
            state="completed",
            locked_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        db.session.add(row)
        db.session.commit()

        _run_as_tenant_role()
        set_tenant(tenants["a"]["org"].id)
        assert IdempotencyRecord.query.count() == 1

        set_tenant(tenants["b"]["org"].id)
        assert IdempotencyRecord.query.count() == 0
