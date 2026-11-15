"""Shared PostgreSQL test harness.

All unit tests that touch the database go through this conftest. We use
a single disposable Postgres schema per session and drop it at teardown.

Per-test isolation is handled by an autouse fixture that TRUNCATEs every
tenant-scoped table after each test. The Flask app itself is
session-scoped so test files can register probe routes once and reuse
them — Flask refuses ``@app.route`` calls after the first request, so
we must set everything up before any test runs.

The schema is built with ``db.metadata.create_all()`` rather than Alembic
because unit tests only need the structural layout; full Alembic replay
is enforced in the CI ``migration-replay`` job.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

os.environ.setdefault("FLASK_CONFIG", "config.Config")
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("FLASK_DEBUG", "0")
os.environ.setdefault(
    "SECRET_KEY", "test-secret-not-for-production-long-enough-for-fernet"
)
os.environ.setdefault(
    "JWT_SECRET_KEY", "test-jwt-secret-not-for-production-long-enough-also"
)


def _admin_url() -> str:
    return os.environ.get(
        "POSTGRES_ADMIN_URL",
        "postgresql://postgres@localhost:5432/postgres",
    )


def _test_url(dbname: str) -> str:
    admin = make_url(_admin_url())
    return str(admin.set(database=dbname))


@pytest.fixture(scope="session")
def _test_database():
    """Return a Postgres URL for the pytest session.

    When ``TRUSTSEAL_PYTEST_SHARED_DB=1`` (used by CI, which runs against
    a pre-provisioned Postgres service container), the existing
    ``DATABASE_URL`` is reused and no CREATE / DROP DATABASE statements
    run — the CI service user often lacks ``CREATEDB``. In that mode we
    still truncate between tests via the autouse fixture, so isolation
    is preserved.

    Otherwise, a disposable per-session database is created and dropped.
    """
    if os.environ.get("TRUSTSEAL_PYTEST_SHARED_DB") == "1":
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError(
                "TRUSTSEAL_PYTEST_SHARED_DB=1 requires DATABASE_URL to be set"
            )
        yield url
        return

    dbname = f"trustseal_pytest_{uuid.uuid4().hex[:12]}"
    admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    try:
        yield _test_url(dbname)
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


def _attach_probe_routes(app):
    """Register every probe route unit tests need, exactly once.

    Flask refuses to add routes after the first request has been
    served. The conftest consolidates probe registration here so test
    files do not have to co-ordinate ordering.
    """
    from flask import abort, g, jsonify

    from app.services.idempotency import idempotent

    # ----- idempotency probes (tests/test_idempotency.py) ---------
    @app.route("/api/_test/idempotent", methods=["POST"])
    @idempotent("test.probe")
    def _idempo_probe():
        app.extensions["_probe_counter"]["count"] += 1
        return jsonify({"calls": app.extensions["_probe_counter"]["count"]}), 201

    @app.route("/api/_test/idempotent-fails", methods=["POST"])
    @idempotent("test.fail")
    def _idempo_fail():
        app.extensions["_probe_counter"]["count"] += 1
        return jsonify({"error": "boom"}), 500

    # ----- observability probe (tests/test_observability.py) ------
    # Served entirely from a before_request so we bypass Flask-Login's
    # redirect without perturbing the api policy. Returning a Response
    # from a before_request short-circuits the rest of the chain and
    # the dispatcher — exactly what we want for an anonymous probe.
    # This before_request was registered AFTER the app factory's own
    # ``before_request_handler``; to ensure we run FIRST, we insert it
    # at the head of the registration list.
    def _obs_probe_short_circuit():
        from flask import request

        if request.path == "/_obs/probe" and request.method == "GET":
            return jsonify({"request_id": g.request_id})
        return None

    # Insert BEFORE ``before_request_handler`` but AFTER the
    # ``_assign_request_id`` observability hook so ``g.request_id`` is
    # bound by the time the short-circuit runs.
    existing = app.before_request_funcs.setdefault(None, [])
    insert_at = next(
        (i for i, fn in enumerate(existing) if fn.__name__ == "before_request_handler"),
        len(existing),
    )
    existing.insert(insert_at, _obs_probe_short_circuit)

    # ----- problem-details probes (tests/test_problem_details.py) -
    @app.route("/api/_test/slug", methods=["POST"])
    def _problem_slug():
        abort(409, description="envelope_not_prepared")

    @app.route("/api/_test/freeform", methods=["POST"])
    def _problem_freeform():
        abort(409, description="Envelope is already finalized on this tenant.")

    @app.route("/api/_test/default", methods=["POST"])
    def _problem_default():
        abort(404)

    @app.route("/api/_test/boom", methods=["POST"])
    def _problem_boom():
        raise RuntimeError("secret internals: SELECT * FROM users")


@pytest.fixture(scope="session")
def _session_app(_test_database):
    """Build the Flask app and create the schema exactly once per session.

    Probe routes used by individual test files are attached here so they
    are present before any test issues a request.
    """
    os.environ["DATABASE_URL"] = _test_database
    from app import create_app
    from app.extensions import db

    created = create_app()
    _attach_probe_routes(created)
    with created.app_context():
        db.create_all()
    yield created
    with created.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def pg_app(_session_app):
    """Per-test app context. Each test gets its own Flask-SQLAlchemy session.

    The app itself is session-scoped so route registrations survive. We
    push a fresh app context per test, which gives Flask-SQLAlchemy a
    clean session at setup and tears it down (committing nothing) at
    teardown. After teardown we TRUNCATE on a dedicated short-lived
    connection — there is no competing transaction at that point because
    the request-scoped session is already closed.
    """
    from app.extensions import db

    ctx = _session_app.app_context()
    ctx.push()
    try:
        yield _session_app
    finally:
        db.session.rollback()
        db.session.remove()
        ctx.pop()
    # TRUNCATE after the app context is popped so no SQLAlchemy session
    # is holding row locks against our clean connection.
    with _session_app.app_context():
        tables = [t for t in db.metadata.sorted_tables if t.name != "alembic_version"]
        if not tables:
            return
        names = ", ".join(f'"{t.name}"' for t in tables)
        with db.engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
