"""Session / device management.

A "session" here is one refresh-token family plus its UI metadata
(device, IP, first-seen, last-seen). The refresh-token service
already owns the cryptographic lifecycle; this module records what a
human needs to recognise and manage their sessions.

Hook points:

* ``record_login(user_id, family_id, request)`` — call from
  ``issue_login_tokens`` right after the family is created.
* ``touch(family_id)`` — call from ``rotate`` to advance
  ``last_seen_at`` so stale sessions age out of the UI.
* ``revoke_by_family(family_id, reason)`` — call from
  ``revoke_all_for_user`` so UI state stays consistent with the
  underlying refresh lifecycle.

Public API:

* ``list_sessions(user_id)`` — active-first listing for the account
  page.
* ``revoke(user_id, session_id, *, reason="user")`` — revoke one
  session; delegates to the refresh-token service so the family also
  dies.
* ``revoke_others(user_id, keep_family_id, *, reason="user")`` —
  "sign out everywhere else" button.

Every revocation emits a SecurityEvent for the audit chain.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from flask import Request

from app.extensions import db
from app.models.event_delivery import SecurityEvent
from app.models.user_session import UserSession


def _client_ip(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    return forwarded or request.remote_addr


def _user_agent(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    agent = request.headers.get("User-Agent", "").strip()
    return agent[:255] or None


def record_login(
    user_id: int, family_id: int, *, request: Optional[Request] = None
) -> UserSession:
    """Open a new UserSession row for a fresh refresh-token family."""
    now = datetime.utcnow()
    row = UserSession(
        user_id=user_id,
        family_id=family_id,
        user_agent=_user_agent(request),
        ip_address=_client_ip(request),
        created_at=now,
        last_seen_at=now,
    )
    db.session.add(row)
    return row


def touch(family_id: int) -> None:
    """Advance ``last_seen_at`` for the session matching ``family_id``."""
    db.session.query(UserSession).filter(
        UserSession.family_id == family_id,
        UserSession.revoked_at.is_(None),
    ).update({"last_seen_at": datetime.utcnow()}, synchronize_session=False)


def revoke_by_family(family_id: int, reason: str = "revoked") -> None:
    """Mark the session that owns ``family_id`` revoked.

    Called indirectly whenever the refresh-token service revokes a
    family (password change, reset, admin revocation, reuse detected).
    """
    now = datetime.utcnow()
    db.session.query(UserSession).filter(
        UserSession.family_id == family_id,
        UserSession.revoked_at.is_(None),
    ).update(
        {"revoked_at": now, "revoke_reason": reason},
        synchronize_session=False,
    )


def list_sessions(user_id: int) -> list[dict]:
    """Return every session (active-first) for the account page."""
    rows = (
        UserSession.query.filter_by(user_id=user_id)
        .order_by(UserSession.revoked_at.is_(None).desc(), UserSession.last_seen_at.desc())
        .all()
    )
    return [
        {
            "id": row.id,
            "user_agent": row.user_agent,
            "ip_address": row.ip_address,
            "device_label": row.device_label,
            "created_at": row.created_at.isoformat(),
            "last_seen_at": row.last_seen_at.isoformat(),
            "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
            "revoke_reason": row.revoke_reason,
            "active": row.revoked_at is None,
        }
        for row in rows
    ]


def revoke(user_id: int, session_id: int, *, reason: str = "user") -> UserSession:
    """Revoke one session; refresh family is revoked as a side-effect."""
    from app.services.refresh_tokens import revoke_family  # local import to avoid cycle
    from app.models.refresh_token import RefreshTokenFamily

    row = db.session.get(UserSession, session_id)
    if row is None or row.user_id != user_id:
        raise LookupError("session_not_found")
    if row.revoked_at is not None:
        return row
    family = db.session.get(RefreshTokenFamily, row.family_id)
    if family is not None and family.revoked_at is None:
        revoke_family(family, reason=reason)
    revoke_by_family(row.family_id, reason)
    _emit_event(user_id, action="session.revoked", resource_id=session_id, outcome="ok")
    return row


def revoke_others(
    user_id: int, keep_family_id: int, *, reason: str = "user"
) -> int:
    """Revoke every active session for the user except ``keep_family_id``.

    Returns the count of sessions revoked.
    """
    from app.services.refresh_tokens import revoke_family  # local import
    from app.models.refresh_token import RefreshTokenFamily

    victims = (
        UserSession.query.filter(
            UserSession.user_id == user_id,
            UserSession.family_id != keep_family_id,
            UserSession.revoked_at.is_(None),
        )
        .all()
    )
    count = 0
    for row in victims:
        family = db.session.get(RefreshTokenFamily, row.family_id)
        if family is not None and family.revoked_at is None:
            revoke_family(family, reason=reason)
        revoke_by_family(row.family_id, reason)
        count += 1
    if count:
        _emit_event(
            user_id, action="session.revoked_others", resource_id=user_id, outcome="ok",
        )
    return count


def _emit_event(
    user_id: int,
    *,
    action: str,
    resource_id: int,
    outcome: str,
) -> None:
    from app.models.user import User

    user = db.session.get(User, user_id)
    event = SecurityEvent(
        organization_id=(user.organization_id if user else None),
        actor_id=user_id,
        action=action,
        resource_type="user_session",
        resource_id=resource_id,
        outcome=outcome,
        correlation_id=uuid.uuid4().hex,
    )
    db.session.add(event)
