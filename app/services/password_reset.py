"""Password reset lifecycle.

Request path (``request_reset``):

* Looks up the user by email. **Enumeration-safe**: returns silently
  whether the email is registered or not. Only when the email matches
  is a token issued and an email sent.
* Revokes prior unconsumed tokens for the user so an in-flight reset
  from an attacker is invalidated by a legitimate second request.

Consume path (``consume``):

* Validates a raw token (constant-time digest compare via DB lookup).
* Rejects unknown, consumed, or expired tokens.
* On success: changes the password, stamps
  ``user.last_password_change_at``, revokes all refresh-token
  families (``revoke_all_for_user(reason="password_reset")``), and
  emits a security event. The caller commits.

Rate limiting is enforced by the HTTP route, not here, so programmatic
callers (migrations, administrative tools) can bypass the cap without
dishonest log messages.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from flask import current_app

from app.extensions import db
from app.models.event_delivery import SecurityEvent
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.services import email as mailer
from app.services.refresh_tokens import revoke_all_for_user

log = logging.getLogger(__name__)

TOKEN_BYTES = 32


class ResetError(Exception):
    """Raised on invalid, expired, consumed, or malformed tokens."""


@dataclass(frozen=True)
class IssueResult:
    user_id: int
    raw_token: str
    expires_at: datetime


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _ttl() -> timedelta:
    minutes = int(current_app.config.get("PASSWORD_RESET_TOKEN_TTL_MINUTES") or 30)
    return timedelta(minutes=minutes)


def _reset_url(raw_token: str) -> str:
    base = (current_app.config.get("PUBLIC_BASE_URL") or "").rstrip("/")
    if not base:
        raise RuntimeError("PUBLIC_BASE_URL is not configured")
    return f"{base}/auth/password-reset/{raw_token}"


def request_reset(
    email: str, *, ip: Optional[str] = None
) -> Optional[IssueResult]:
    """Issue a reset token if the email matches an active user.

    Returns the issue result (useful for tests). Production callers
    discard the return value — the user receives the token via email
    only.
    """
    if not isinstance(email, str) or "@" not in email:
        return None
    normalized = email.strip().lower()
    user = User.query.filter_by(email=normalized).one_or_none()
    if user is None or not user.is_active:
        return None
    now = datetime.utcnow()
    db.session.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.consumed_at.is_(None),
    ).update({"consumed_at": now}, synchronize_session=False)
    raw_token = secrets.token_urlsafe(TOKEN_BYTES)
    expires_at = now + _ttl()
    row = PasswordResetToken(
        user_id=user.id,
        token_sha256=_hash_token(raw_token),
        issued_at=now,
        expires_at=expires_at,
        issued_from_ip=ip,
    )
    db.session.add(row)
    _send_email(user, raw_token, expires_at)
    _emit_security_event(user, action="password_reset.requested", outcome="ok")
    return IssueResult(user_id=user.id, raw_token=raw_token, expires_at=expires_at)


def consume(raw_token: str, *, new_password: str) -> User:
    """Consume ``raw_token`` and set the owning user's password.

    Returns the user. Caller commits. Revokes every outstanding
    refresh-token family so stolen pre-reset tokens cannot survive.
    """
    if not isinstance(raw_token, str) or len(raw_token) < 20 or len(raw_token) > 128:
        raise ResetError("token_malformed")
    if not isinstance(new_password, str) or not 12 <= len(new_password) <= 1024:
        raise ResetError("new_password_strength")
    row = (
        db.session.query(PasswordResetToken)
        .filter_by(token_sha256=_hash_token(raw_token))
        .one_or_none()
    )
    if row is None:
        raise ResetError("token_unknown")
    if row.consumed_at is not None:
        raise ResetError("token_consumed")
    now = datetime.utcnow()
    if row.expires_at < now:
        raise ResetError("token_expired")
    user = db.session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise ResetError("user_inactive")
    if user.check_password(new_password):
        raise ResetError("new_password_must_differ")
    user.set_password(new_password)
    user.last_password_change_at = now
    row.consumed_at = now
    revoke_all_for_user(user.id, reason="password_reset")
    _emit_security_event(user, action="password_reset.consumed", outcome="ok")
    return user


def _emit_security_event(user: User, *, action: str, outcome: str) -> None:
    event = SecurityEvent(
        organization_id=user.organization_id,
        actor_id=user.id,
        action=action,
        resource_type="user",
        resource_id=user.id,
        outcome=outcome,
        correlation_id=uuid.uuid4().hex,
    )
    db.session.add(event)


def _send_email(user: User, raw_token: str, expires_at: datetime) -> None:
    url = _reset_url(raw_token)
    display = user.first_name or user.username or user.email
    subject = "Reset your TrustSeal password"
    text = (
        f"Hello {display},\n\n"
        "A password reset was requested for your TrustSeal account. "
        "If this was you, follow the link below within "
        f"{(expires_at - datetime.utcnow()).seconds // 60} minutes to set "
        "a new password:\n\n"
        f"{url}\n\n"
        "If you did not request this, you can ignore this email — your "
        "password will not change. Consider enabling MFA from "
        "your account security settings.\n\n"
        "— The TrustSeal team"
    )
    html = (
        f"<p>Hello {_esc(display)},</p>"
        "<p>A password reset was requested for your TrustSeal "
        "account. If this was you, follow the link below to set a new "
        "password:</p>"
        f'<p><a href="{_esc(url)}">{_esc(url)}</a></p>'
        "<p>If you did not request this, you can ignore this email — "
        "your password will not change. Consider enabling MFA from "
        "your account security settings.</p>"
        "<p>— The TrustSeal team</p>"
    )
    mailer.send(
        mailer.EmailMessage(
            to=user.email,
            subject=subject,
            body_text=text,
            body_html=html,
        )
    )


def _esc(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
