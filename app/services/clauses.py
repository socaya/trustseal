"""Clause library service.

Public API:

* ``create_clause(organization_id, name, body, created_by_id,
  category=None)`` — new clause with v1 draft.
* ``new_version(clause, body, author_id)`` — refused on archived
  clauses; on approved clauses the caller must call
  ``reopen(clause, author_id)`` first.
* ``reopen(clause, author_id)`` — approved → draft.
* ``approve(clause, approved_by_id)`` — flip state; author must be
  different (separation of duties, enforced at HTTP layer).
* ``archive(clause, archived_by_id)`` — terminal state.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from app.extensions import db
from app.models.clause import Clause, ClauseVersion
from app.models.event_delivery import SecurityEvent


class ClauseError(Exception):
    """Policy violation in the clause service."""


def _emit(
    *,
    actor_id: int,
    organization_id: Optional[int],
    action: str,
    resource_id: int,
    outcome: str = "ok",
) -> None:
    db.session.add(
        SecurityEvent(
            organization_id=organization_id,
            actor_id=actor_id,
            action=action,
            resource_type="clause",
            resource_id=resource_id,
            outcome=outcome,
            correlation_id=uuid.uuid4().hex,
        )
    )


def create_clause(
    organization_id: int,
    name: str,
    body: str,
    *,
    created_by_id: int,
    category: Optional[str] = None,
) -> Clause:
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200:
        raise ClauseError("name_invalid")
    body = body or ""
    clause = Clause(
        organization_id=organization_id,
        name=name.strip(),
        category=category,
        state="draft",
        created_by_id=created_by_id,
    )
    db.session.add(clause)
    db.session.flush()
    version = ClauseVersion(
        clause_id=clause.id,
        revision=1,
        body=body,
        created_by_id=created_by_id,
    )
    db.session.add(version)
    db.session.flush()
    clause.current_version_id = version.id
    _emit(
        actor_id=created_by_id,
        organization_id=organization_id,
        action="clause.created",
        resource_id=clause.id,
    )
    return clause


def new_version(
    clause: Clause, body: str, *, author_id: int
) -> ClauseVersion:
    if clause.state == "archived":
        raise ClauseError("clause_archived")
    if clause.state == "approved":
        raise ClauseError("reopen_before_new_version")
    current_max = (
        db.session.query(db.func.max(ClauseVersion.revision))
        .filter_by(clause_id=clause.id)
        .scalar()
        or 0
    )
    version = ClauseVersion(
        clause_id=clause.id,
        revision=current_max + 1,
        body=(body or ""),
        created_by_id=author_id,
    )
    db.session.add(version)
    db.session.flush()
    clause.current_version_id = version.id
    _emit(
        actor_id=author_id,
        organization_id=clause.organization_id,
        action="clause.version_added",
        resource_id=clause.id,
    )
    return version


def reopen(clause: Clause, *, author_id: int) -> Clause:
    if clause.state != "approved":
        raise ClauseError("only_approved_clauses_can_reopen")
    clause.state = "draft"
    _emit(
        actor_id=author_id,
        organization_id=clause.organization_id,
        action="clause.reopened",
        resource_id=clause.id,
    )
    return clause


def approve(clause: Clause, *, approved_by_id: int) -> Clause:
    if clause.state == "archived":
        raise ClauseError("clause_archived")
    if clause.state == "approved":
        return clause
    if clause.current_version_id is None:
        raise ClauseError("no_current_version")
    now = datetime.utcnow()
    clause.state = "approved"
    clause.approved_at = now
    clause.approved_by_id = approved_by_id
    version = db.session.get(ClauseVersion, clause.current_version_id)
    if version is not None and version.approved_at is None:
        version.approved_at = now
        version.approved_by_id = approved_by_id
    _emit(
        actor_id=approved_by_id,
        organization_id=clause.organization_id,
        action="clause.approved",
        resource_id=clause.id,
    )
    return clause


def archive(clause: Clause, *, archived_by_id: int) -> Clause:
    if clause.state == "archived":
        return clause
    clause.state = "archived"
    clause.archived_at = datetime.utcnow()
    clause.archived_by_id = archived_by_id
    _emit(
        actor_id=archived_by_id,
        organization_id=clause.organization_id,
        action="clause.archived",
        resource_id=clause.id,
    )
    return clause
