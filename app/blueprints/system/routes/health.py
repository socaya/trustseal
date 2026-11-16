"""Liveness + readiness probes (N3).

* ``GET /health`` — cheap liveness check. Returns 200 unless the
  process itself is incapable of answering (handled by the load
  balancer). No DB, no I/O.
* ``GET /ready`` — readiness check that fails fast when a direct
  dependency is unavailable:

    - PostgreSQL round-trip (``SELECT 1``).
    - Alembic head matches the migration directory head.
    - ``PRIVATE_DOCUMENT_ROOT`` exists with mode ``0700``.
    - ``MAIL_TRANSPORT`` is one of the supported values.

Both endpoints are intentionally outside the authenticated API
surface so k8s probes don't need a bearer token.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

from app.extensions import db


health_bp = Blueprint("health_bp", __name__)


@health_bp.route("/health", methods=["GET"])
def health():
    return jsonify(status="ok"), 200


@health_bp.route("/ready", methods=["GET"])
def ready():
    checks: list[dict] = []
    overall = True
    checks.append(_db_check())
    checks.append(_migrations_check())
    checks.append(_private_storage_check())
    checks.append(_mail_transport_check())
    for c in checks:
        if c["status"] != "ok":
            overall = False
            break
    body = jsonify(status="ok" if overall else "degraded", checks=checks)
    return body, (200 if overall else 503)


def _db_check() -> dict:
    try:
        db.session.execute(text("SELECT 1"))
        return {"name": "database", "status": "ok"}
    except Exception as exc:
        return {
            "name": "database",
            "status": "failed",
            "detail": _redact(exc),
        }


def _migrations_check() -> dict:
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from alembic.runtime.migration import MigrationContext
    except ImportError:
        return {"name": "migrations", "status": "skipped"}
    try:
        cfg = Config()
        migrations_dir = Path(__file__).resolve().parents[4] / "migrations"
        cfg.set_main_option("script_location", str(migrations_dir))
        script = ScriptDirectory.from_config(cfg)
        expected_heads = set(script.get_heads())
        with db.engine.connect() as connection:
            ctx = MigrationContext.configure(connection)
            current = set(ctx.get_current_heads())
        if expected_heads == current:
            return {"name": "migrations", "status": "ok"}
        return {
            "name": "migrations",
            "status": "behind",
            "expected": sorted(expected_heads),
            "current": sorted(current),
        }
    except Exception as exc:
        return {
            "name": "migrations",
            "status": "failed",
            "detail": _redact(exc),
        }


def _private_storage_check() -> dict:
    """Delegate to the active storage adapter's probe (Phase O3)."""
    try:
        from app.services.documents.private_object_store import active_store

        store = active_store()
    except Exception as exc:
        return {
            "name": "private_storage",
            "status": "failed",
            "detail": _redact(exc),
        }
    try:
        payload = dict(store.probe(config=current_app.config))
    except Exception as exc:
        return {
            "name": "private_storage",
            "status": "failed",
            "detail": _redact(exc),
        }
    payload["name"] = "private_storage"
    return payload


def _mail_transport_check() -> dict:
    transport = (current_app.config.get("MAIL_TRANSPORT") or "").lower()
    if transport not in ("smtp", "memory"):
        return {
            "name": "mail_transport",
            "status": "failed",
            "detail": f"unknown_transport:{transport!r}",
        }
    return {"name": "mail_transport", "status": "ok"}


def _redact(exc: Exception) -> str:
    text = str(exc)
    if len(text) > 160:
        return text[:160] + "…"
    return text
