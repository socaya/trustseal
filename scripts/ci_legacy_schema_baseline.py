"""Create disposable current-legacy schema to test *new* Alembic revisions.

The repository's first 2025 migration is ALTER-only and cannot bootstrap a
fresh database. This script does NOT claim to reproduce a historical backup.

Rather than hand-maintain a list of trust-service tables added after
revision ``1856829bd7b1`` (the pre-2026 legacy head), the script scans
the migration chain and extracts every table name that appears in an
``op.create_table(...)`` call downstream of the legacy head. Those
names are excluded from the ``create_all`` baseline and the migrations
that follow create them.

If a new migration introduces a ``create_table`` call for a table the
scanner misses, update the legacy head constant below rather than
patch a hand-maintained allowlist.

Only run in GitHub CI against the disposable ``trustseal_ci`` database.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from sqlalchemy import inspect

from app import create_app
from app.extensions import db

LEGACY_HEAD_REVISION = "1856829bd7b1"
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations" / "versions"
_TABLE_RE = re.compile(r"""op\.create_table\(\s*["']([^"']+)["']""")
_REV_RE = re.compile(r"""^revision\s*(?::[^=]+)?=\s*["']([^"']+)["']""", re.MULTILINE)
_DOWN_LINE_RE = re.compile(r"""^down_revision\s*(?::[^=]+)?=\s*(.+)$""", re.MULTILINE)
_QUOTED_STR_RE = re.compile(r"""["']([^"']+)["']""")


def _parse_down_revisions(text: str) -> list[str]:
    match = _DOWN_LINE_RE.search(text)
    if match is None:
        return []
    rhs = match.group(1).strip()
    if rhs.startswith("None"):
        return []
    return _QUOTED_STR_RE.findall(rhs)


def _load_migration_graph() -> dict[str, dict]:
    """Return ``{revision: {"downs": [str, ...], "tables": [str, ...]}}``."""
    graph: dict[str, dict] = {}
    for path in MIGRATIONS_DIR.glob("*.py"):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        rev = _REV_RE.search(text)
        if rev is None:
            continue
        graph[rev.group(1)] = {
            "downs": _parse_down_revisions(text),
            "tables": _TABLE_RE.findall(text),
        }
    return graph


def _descendants_of(root: str, graph: dict[str, dict]) -> set[str]:
    """Return the set of revisions reachable from ``root`` via ``downs``.

    Every revision whose ancestry passes through ``root`` (exclusive),
    including merge revisions with tuple ``down_revision``, is considered a
    descendant. The script treats ``1856829bd7b1`` as the legacy ceiling —
    anything in its downstream set created trust-service tables that CI must
    NOT pre-create.
    """
    out: set[str] = set()
    for rev, meta in graph.items():
        if rev == root:
            continue
        stack = list(meta["downs"])
        visited: set[str] = set()
        while stack:
            cursor = stack.pop()
            if cursor == root:
                out.add(rev)
                break
            if cursor in visited:
                continue
            visited.add(cursor)
            stack.extend(graph.get(cursor, {}).get("downs", []))
    return out


def compute_new_tables() -> set[str]:
    graph = _load_migration_graph()
    if LEGACY_HEAD_REVISION not in graph:
        raise SystemExit(
            f"Legacy head revision {LEGACY_HEAD_REVISION!r} not found; "
            "update LEGACY_HEAD_REVISION or verify the migration chain."
        )
    downstream = _descendants_of(LEGACY_HEAD_REVISION, graph)
    tables: set[str] = set()
    for rev in downstream:
        tables.update(graph[rev]["tables"])
    return tables


def main():
    if os.getenv("CI") != "true" or os.getenv("FLASK_ENV") != "testing":
        raise SystemExit("Refusing legacy-baseline setup outside isolated CI")
    url = os.getenv("DATABASE_URL", "")
    if not url.endswith("@localhost:5432/trustseal_ci"):
        raise SystemExit("CI baseline requires disposable trustseal_ci database")
    app = create_app()
    with app.app_context():
        existing = inspect(db.engine).get_table_names()
        if existing:
            raise SystemExit("Refusing baseline creation on a nonempty database")
        new_tables = compute_new_tables()
        table_list = [
            table for name, table in db.metadata.tables.items()
            if name not in new_tables
        ]
        db.metadata.create_all(bind=db.engine, tables=table_list)
        print("CI legacy-model baseline tables created:", len(table_list))
        print("Excluded trust-service tables:", len(new_tables))


if __name__ == "__main__":
    main()
