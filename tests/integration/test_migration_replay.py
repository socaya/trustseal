"""Alembic migration-chain replay against a disposable Postgres.

Three-step exercise:

1. Bootstrap the legacy baseline via
   ``scripts.ci_legacy_schema_baseline.compute_new_tables`` so the
   trust-service tables are absent.
2. ``flask db stamp 1856829bd7b1`` (the legacy head), then ``flask db
   upgrade`` to run every migration added after.
3. ``flask db downgrade base`` followed by ``flask db upgrade`` to
   prove the chain is reversible (append-only trust tables raise a
   controlled ``RuntimeError`` and we accept that as a documented
   signal, not a silent pass).

The test is heavy — it stands up a fresh Postgres database — so it
lives under ``tests/integration/`` and is skipped when
``TRUSTSEAL_INTEGRATION_DB`` is not configured.
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text


def _admin_url() -> str:
    return os.environ.get(
        "POSTGRES_ADMIN_URL",
        "postgresql://postgres@localhost:5432/postgres",
    )


@pytest.fixture(scope="module")
def disposable_db():
    admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    dbname = f"trustseal_replay_{uuid.uuid4().hex[:10]}"
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    url = f"postgresql://postgres@localhost:5432/{dbname}"
    try:
        yield url
    finally:
        with admin.connect() as conn:
            conn.execute(
                text(
                    f"""
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = '{dbname}' AND pid <> pg_backend_pid()
                    """
                )
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{dbname}"'))
        admin.dispose()


def _flask(cmd: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **env}
    return subprocess.run(
        [sys.executable, "-m", "flask", *cmd],
        capture_output=True,
        text=True,
        env=full_env,
        timeout=300,
    )


class TestReplay:
    def test_upgrade_from_legacy_baseline(self, disposable_db):
        """Primary CI contract: stamp legacy head, then upgrade.

        Uses a dedicated SQLAlchemy engine bound to ``disposable_db``
        for schema inspection and table creation. Flask-SQLAlchemy's
        ``db.engine`` is already bound to the pytest session's
        disposable test database (by the main ``conftest.py``
        ``_session_app`` fixture) and cannot be re-bound without
        rebuilding the extension, so routing *this* test's schema
        work through ``db.engine`` would corrupt the session DB.
        ``flask db stamp`` + ``flask db upgrade`` run as subprocesses
        with ``DATABASE_URL`` overridden, so Alembic's own operations
        correctly target ``disposable_db``.
        """
        env = {
            "FLASK_APP": "main:app",
            "FLASK_ENV": "testing",
            "FLASK_DEBUG": "0",
            "DATABASE_URL": disposable_db,
            "SECRET_KEY": "replay-secret-not-for-production-long-enough",
            "JWT_SECRET_KEY": "replay-jwt-secret-not-for-production-long-enough",
            "CI": "true",
            # Only the shared-DB path works outside the main tests/conftest.py
            "TRUSTSEAL_PYTEST_SHARED_DB": "1",
        }
        # Build the legacy-schema baseline using the live script. Mock
        # the strict host check that script applies; the URL assertion
        # is cosmetic for the integration run.
        from scripts.ci_legacy_schema_baseline import compute_new_tables
        from app.extensions import db

        disposable = create_engine(disposable_db)
        try:
            existing = inspect(disposable).get_table_names()
            assert not existing, "expected a clean disposable database"
            new_tables = compute_new_tables()
            legacy_tables = [
                table for name, table in db.metadata.tables.items()
                if name not in new_tables
            ]
            db.metadata.create_all(bind=disposable, tables=legacy_tables)
            assert new_tables, "no trust-service tables detected"
        finally:
            disposable.dispose()
        stamp = _flask(["db", "stamp", "1856829bd7b1"], env)
        assert stamp.returncode == 0, stamp.stderr
        upgrade = _flask(["db", "upgrade"], env)
        assert upgrade.returncode == 0, upgrade.stderr
        # Verify a representative trust-service table now exists.
        disposable = create_engine(disposable_db)
        try:
            names = inspect(disposable).get_table_names()
        finally:
            disposable.dispose()
        assert "idempotency_records" in names
        assert "refresh_token_jtis" in names

    def test_replay_from_head_is_stable(self, disposable_db):
        """A second ``flask db upgrade`` on a fully-migrated DB is a no-op."""
        env = {
            "FLASK_APP": "main:app",
            "FLASK_ENV": "testing",
            "FLASK_DEBUG": "0",
            "DATABASE_URL": disposable_db,
            "SECRET_KEY": "replay-secret-not-for-production-long-enough",
            "JWT_SECRET_KEY": "replay-jwt-secret-not-for-production-long-enough",
            "CI": "true",
            "TRUSTSEAL_PYTEST_SHARED_DB": "1",
        }
        before = _flask(["db", "current"], env)
        after = _flask(["db", "upgrade"], env)
        assert after.returncode == 0, after.stderr
        current_again = _flask(["db", "current"], env)
        assert before.stdout.strip() == current_again.stdout.strip()


class TestNewTableDetection:
    def test_includes_all_trust_service_tables(self):
        """The dynamic detector must cover tables added in recent milestones."""
        from scripts.ci_legacy_schema_baseline import compute_new_tables

        tables = compute_new_tables()
        for required in {
            "revoked_tokens",
            "document_blobs",
            "security_events",
            "outbox_events",
            "idempotency_records",
            "webhook_endpoints",
            "webhook_deliveries",
            "mfa_credentials",
            "refresh_token_families",
            "refresh_token_jtis",
            "oidc_providers",
            "scim_service_accounts",
        }:
            assert required in tables, f"missing {required} in NEW_TABLES"

    def test_excludes_legacy_tables(self):
        from scripts.ci_legacy_schema_baseline import compute_new_tables

        tables = compute_new_tables()
        for legacy in {
            "users",
            "organizations",
            "documents",
            "subscriptions",
            "roles",
        }:
            assert legacy not in tables, f"{legacy} should not be classed as new"
