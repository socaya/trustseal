"""Issue, rotate, and revoke refresh-token families.

The semantics here enforce three invariants that matter in a real
deployment:

1. **One active jti per family.** Only the most recently issued refresh
   ``jti`` in a family may be redeemed. Rotation is atomic: inserting
   the new row and marking the old one revoked happens in a single DB
   transaction.
2. **Reuse detection.** If a jti that was already rotated/revoked is
   presented at ``/api/auth/refresh``, the whole family is marked
   revoked and a ``security_events`` row is emitted. This mirrors the
   OAuth 2.0 RFC 6819 recommendation and gives operators a loud signal
   that a refresh token has been captured.
3. **Password-change revokes everything.** When a user rotates their
   password every family is revoked synchronously; subsequent access
   or refresh tokens issued before the change fail the blocklist
   check.

Call sites are the authentication blueprint and the password-change
endpoint. Both run inside a Flask request context.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from flask import current_app
from flask_jwt_extended import create_access_token, create_refresh_token, decode_token

from app.extensions import db
from app.models.refresh_token import RefreshTokenFamily, RefreshTokenJti
from app.models.revoked_token import RevokedToken


def _refresh_expires_at(now: datetime) -> datetime:
    """Return the wall-clock expiry of a refresh token for revocation records."""
    expires_delta = current_app.config.get("JWT_REFRESH_TOKEN_EXPIRES")
    if not isinstance(expires_delta, timedelta):
        expires_delta = timedelta(days=30)
    return now + expires_delta


def _new_family(user_id: int) -> RefreshTokenFamily:
    family = RefreshTokenFamily(user_id=user_id, created_at=datetime.utcnow())
    db.session.add(family)
    db.session.flush()
    return family


def _record_jti(jti: str, family: RefreshTokenFamily) -> None:
    db.session.add(
        RefreshTokenJti(
            jti=jti,
            family_id=family.id,
            user_id=family.user_id,
            created_at=datetime.utcnow(),
        )
    )
    db.session.flush()


def issue_login_tokens(user_id: int) -> tuple[str, str]:
    """Issue a fresh access + refresh pair in a new family.

    Returns ``(access_token, refresh_token)``. The caller must commit
    the surrounding transaction.
    """
    family = _new_family(user_id)
    access = create_access_token(identity=str(user_id))
    refresh = create_refresh_token(
        identity=str(user_id), additional_claims={"fam": family.id}
    )
    jti = decode_token(refresh)["jti"]
    _record_jti(jti, family)
    return access, refresh


def rotate(current_jwt: dict) -> tuple[str, str]:
    """Rotate a refresh token.

    ``current_jwt`` is the decoded payload of the refresh JWT presented
    to ``/api/auth/refresh``. Returns a new ``(access_token, refresh_token)``
    pair on success or raises :class:`ReuseDetected` / :class:`RefreshRejected`.
    """
    jti = current_jwt.get("jti")
    family_id = current_jwt.get("fam")
    identity = current_jwt.get("sub")
    if not isinstance(jti, str) or not isinstance(family_id, int) or not identity:
        raise RefreshRejected("malformed_refresh_token")

    row = db.session.get(RefreshTokenJti, jti)
    if row is None:
        raise RefreshRejected("unknown_refresh_token")
    if row.family_id != family_id or str(row.user_id) != str(identity):
        raise RefreshRejected("refresh_token_claims_inconsistent")

    family = db.session.get(RefreshTokenFamily, family_id)
    if family is None or family.revoked_at is not None:
        raise RefreshRejected("refresh_token_family_revoked")

    if row.revoked_at is not None:
        revoke_family(family, reason="reuse_detected")
        raise ReuseDetected(family_id=family.id, user_id=row.user_id)

    now = datetime.utcnow()
    row.rotated_at = now
    row.revoked_at = now
    # Also record the old jti in RevokedToken so flask_jwt_extended's
    # blocklist callback rejects subsequent presentations of it.
    db.session.add(
        RevokedToken(
            jti=jti,
            user_id=row.user_id,
            expires_at=_refresh_expires_at(now).replace(tzinfo=timezone.utc),
        )
    )

    access = create_access_token(identity=str(row.user_id))
    refresh = create_refresh_token(
        identity=str(row.user_id),
        additional_claims={"fam": family.id},
    )
    new_jti = decode_token(refresh)["jti"]
    _record_jti(new_jti, family)
    return access, refresh


def revoke_family(family: RefreshTokenFamily, *, reason: str) -> None:
    """Mark the family and every live jti in it as revoked.

    Emits a security event when ``reason`` indicates reuse so operators
    can alert on it.
    """
    if family.revoked_at is not None:
        return
    now = datetime.utcnow()
    family.revoked_at = now
    family.revoke_reason = reason[:80]
    # Revoke every outstanding jti in the family.
    rows = RefreshTokenJti.query.filter_by(
        family_id=family.id, revoked_at=None
    ).all()
    for row in rows:
        row.revoked_at = now
        db.session.add(
            RevokedToken(
                jti=row.jti,
                user_id=row.user_id,
                expires_at=_refresh_expires_at(now).replace(tzinfo=timezone.utc),
            )
        )
    db.session.flush()
    _emit_security_event(family.user_id, reason)


def revoke_all_for_user(user_id: int, *, reason: str) -> int:
    """Revoke every outstanding family for ``user_id``.

    Returns the number of families revoked. Called from password
    change and from administrative session-revocation flows.
    """
    families = RefreshTokenFamily.query.filter_by(
        user_id=user_id, revoked_at=None
    ).all()
    for family in families:
        revoke_family(family, reason=reason)
    return len(families)


def _emit_security_event(user_id: int, reason: str) -> None:
    import uuid

    from app.models.event_delivery import SecurityEvent

    db.session.add(
        SecurityEvent(
            organization_id=_tenant_for(user_id),
            actor_id=user_id,
            action=f"refresh.{reason}",
            resource_type="refresh_token_family",
            resource_id=user_id,
            outcome="rejected" if reason == "reuse_detected" else "revoked",
            correlation_id=uuid.uuid4().hex,
        )
    )


def _tenant_for(user_id: int) -> Optional[int]:
    from app.models.user import User

    user = db.session.get(User, user_id)
    return user.organization_id if user else None


# ----- exceptions ---------------------------------------------------


class RefreshRejected(RuntimeError):
    """Refresh token cannot be redeemed for structural or policy reasons."""


class ReuseDetected(RuntimeError):
    """A replayed refresh ``jti`` triggered family-wide revocation."""

    def __init__(self, *, family_id: int, user_id: int) -> None:
        super().__init__("refresh_token_reuse_detected")
        self.family_id = family_id
        self.user_id = user_id
