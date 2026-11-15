"""Team membership service.

Public functions:

* ``create_team(organization_id, name, created_by_id, description=None)``
* ``archive_team(team_id, archived_by_id)`` — soft-delete
* ``add_member(team_id, user_id, added_by_id, role_in_team="member")``
* ``remove_member(team_id, user_id, removed_by_id)``
* ``membership_ids(user_id)`` — active team ids the user belongs to
* ``members(team_id)`` — active member ids for a team

Every mutation emits a SecurityEvent so the audit chain captures who
added/removed whom. Soft-delete preserves historical membership for
investigation.

Separation-of-duties: an admin can create and add themselves to a
team they created, since team membership is advisory; but the SoD
module remains available for team-scoped privileged actions once a
product policy defines them.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Iterable, Optional

from app.extensions import db
from app.models.event_delivery import SecurityEvent
from app.models.team import Team, TeamMembership
from app.models.user import User


class TeamError(Exception):
    """Raised for policy violations in the team service."""


def create_team(
    organization_id: int,
    name: str,
    *,
    created_by_id: int,
    description: Optional[str] = None,
) -> Team:
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        raise TeamError("team_name_invalid")
    row = Team(
        organization_id=organization_id,
        name=name.strip(),
        description=(description or None),
        created_by_id=created_by_id,
    )
    db.session.add(row)
    db.session.flush()
    _emit(
        action="team.created",
        actor_id=created_by_id,
        organization_id=organization_id,
        resource_type="team",
        resource_id=row.id,
    )
    return row


def archive_team(team_id: int, *, archived_by_id: int) -> Team:
    row = db.session.get(Team, team_id)
    if row is None:
        raise TeamError("team_not_found")
    if row.deleted_at is not None:
        return row
    row.deleted_at = datetime.utcnow()
    # Also remove every active membership so subsequent visibility
    # lookups exclude the archived team.
    db.session.query(TeamMembership).filter(
        TeamMembership.team_id == team_id,
        TeamMembership.removed_at.is_(None),
    ).update(
        {
            "removed_at": row.deleted_at,
            "removed_by_id": archived_by_id,
        },
        synchronize_session=False,
    )
    _emit(
        action="team.archived",
        actor_id=archived_by_id,
        organization_id=row.organization_id,
        resource_type="team",
        resource_id=row.id,
    )
    return row


def add_member(
    team_id: int,
    user_id: int,
    *,
    added_by_id: int,
    role_in_team: str = "member",
) -> TeamMembership:
    team = db.session.get(Team, team_id)
    if team is None or team.deleted_at is not None:
        raise TeamError("team_not_found")
    user = db.session.get(User, user_id)
    if user is None or not user.is_active:
        raise TeamError("user_not_found")
    if user.organization_id != team.organization_id:
        raise TeamError("user_wrong_organization")
    existing = TeamMembership.query.filter_by(
        team_id=team_id, user_id=user_id, removed_at=None
    ).one_or_none()
    if existing is not None:
        return existing
    role_norm = (role_in_team or "member").strip().lower() or "member"
    if len(role_norm) > 40:
        raise TeamError("role_in_team_too_long")
    row = TeamMembership(
        team_id=team_id,
        user_id=user_id,
        role_in_team=role_norm,
        added_by_id=added_by_id,
        added_at=datetime.utcnow(),
    )
    db.session.add(row)
    db.session.flush()
    _emit(
        action="team.member_added",
        actor_id=added_by_id,
        organization_id=team.organization_id,
        resource_type="team_membership",
        resource_id=row.id,
    )
    return row


def remove_member(
    team_id: int, user_id: int, *, removed_by_id: int
) -> TeamMembership:
    row = TeamMembership.query.filter_by(
        team_id=team_id, user_id=user_id, removed_at=None
    ).one_or_none()
    if row is None:
        raise TeamError("membership_not_found")
    row.removed_at = datetime.utcnow()
    row.removed_by_id = removed_by_id
    team = db.session.get(Team, team_id)
    _emit(
        action="team.member_removed",
        actor_id=removed_by_id,
        organization_id=(team.organization_id if team else None),
        resource_type="team_membership",
        resource_id=row.id,
    )
    return row


def membership_ids(user_id: int) -> list[int]:
    """Return the active team ids a user belongs to."""
    rows = (
        db.session.query(TeamMembership.team_id)
        .filter(
            TeamMembership.user_id == user_id,
            TeamMembership.removed_at.is_(None),
        )
        .all()
    )
    return [r[0] for r in rows]


def members(team_id: int) -> list[int]:
    """Return the active member user-ids of a team."""
    rows = (
        db.session.query(TeamMembership.user_id)
        .filter(
            TeamMembership.team_id == team_id,
            TeamMembership.removed_at.is_(None),
        )
        .all()
    )
    return [r[0] for r in rows]


def _emit(
    *,
    action: str,
    actor_id: int,
    organization_id: Optional[int],
    resource_type: str,
    resource_id: int,
) -> None:
    db.session.add(
        SecurityEvent(
            organization_id=organization_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome="ok",
            correlation_id=uuid.uuid4().hex,
        )
    )
