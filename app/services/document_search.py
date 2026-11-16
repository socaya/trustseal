"""Tenant-scoped full-text search across documents.

Uses Postgres' built-in ``to_tsvector('english', ...)`` lexer plus
``plainto_tsquery`` so the query:

* respects stemming ("seal" matches "sealing", "sealed"),
* strips stop-words,
* is deterministic and portable across environments,
* works without any additional stored column or index — tests run
  on ``db.create_all()`` without touching Alembic triggers.

For large deployments the followup is to add a stored ``search_vector``
column + GIN index. The query here would then prefer the stored
column when the migration is in place and fall back to the inline
``to_tsvector`` otherwise.

Results are ranked by ``ts_rank`` (descending) and capped by the
caller-supplied limit (default 50, max 200). Tenant isolation is
always enforced; a caller cannot search across tenants.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text

from app.extensions import db

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


@dataclass(frozen=True)
class SearchHit:
    document_id: int
    title: str
    description: Optional[str]
    rank: float
    created_at: Optional[str]
    status: Optional[str]


def search(
    organization_id: int,
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
) -> list[SearchHit]:
    """Return ranked hits for ``query`` within one tenant.

    Empty / whitespace-only queries return an empty list rather than
    an error, so a prefix-search UI can send characters freely without
    paying a round-trip on each keystroke.
    """
    if not isinstance(query, str) or not query.strip():
        return []
    capped = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    rows = db.session.execute(
        text(
            """
            SELECT
                id,
                title,
                description,
                status,
                created_at,
                ts_rank(
                    to_tsvector(
                        'english',
                        COALESCE(title, '') || ' ' || COALESCE(description, '')
                    ),
                    plainto_tsquery('english', :q)
                ) AS rank
            FROM documents
            WHERE organization_id = :org
              AND deleted_at IS NULL
              AND to_tsvector(
                    'english',
                    COALESCE(title, '') || ' ' || COALESCE(description, '')
              ) @@ plainto_tsquery('english', :q)
            ORDER BY rank DESC, id DESC
            LIMIT :lim
            """
        ),
        {"q": query.strip(), "org": organization_id, "lim": capped},
    ).all()
    return [
        SearchHit(
            document_id=row.id,
            title=row.title,
            description=row.description,
            rank=float(row.rank),
            created_at=row.created_at.isoformat() if row.created_at else None,
            status=row.status,
        )
        for row in rows
    ]
