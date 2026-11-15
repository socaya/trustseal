"""Email verification lifecycle.

Issuing a token:

* ``issue(user, *, ip=None)`` revokes every prior unconsumed token
  for the user, generates a fresh 256-bit token, stores its SHA-256
  digest, and sends a verification email. The raw token is returned
  so the caller (register / resend routes) can embed it in the
  outbound link. The DB never stores the raw value.

Consuming a token:

* ``consume(raw_token)`` returns the owning ``User`` and stamps the
  token ``consumed_at``. Refuses if the token is unknown, expired,
  already consumed, or if the user's current email no longer
  matches the email the token was issued against. On success the
  caller is responsible for committing.

Resending:

* ``resend(user, *, ip=None)`` is just ``issue`` with a different
  name and is rate-limited by the caller using
  :func:`app.services.rate_limiting.consume`.

Policy:

* The user record retains ``email_verified=False`` until the token
  is successfully consumed; successful consumption sets
  ``email_verified=True`` and stamps ``email_verified_at``.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from flask import current_app

from app.extensions import db
from app.models.email_verification_token import EmailVerificationToken
from app.models.event_delivery import SecurityEvent
from app.models.user import User
from app.services import email as mailer

log = logging.getLogger(__name__)

TOKEN_BYTES = 32  # 256 bits — plenty of entropy for a one-shot link.


class VerificationError(Exception):
    """Raised when a token is invalid, expired, consumed, or mismatched."""


@dataclass(frozen=True)
class IssueResult:
    user_id: int
    raw_token: str
    expires_at: datetime


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _ttl() -> timedelta:
    hours = int(current_app.config.get("EMAIL_VERIFICATION_TOKEN_TTL_HOURS") or 48)
    return timedelta(hours=hours)


def _verify_url(raw_token: str) -> str:
    base = (current_app.config.get("PUBLIC_BASE_URL") or "").rstrip("/")
    if not base:
        raise RuntimeError("PUBLIC_BASE_URL is not configured")
    return f"{base}/auth/verify-email/{raw_token}"


def issue(user: User, *, ip: Optional[str] = None) -> IssueResult:
    """Revoke prior unconsumed tokens for the user, create a fresh one, send the email."""
    if user.email_verified:
        raise VerificationError("already_verified")
    now = datetime.utcnow()
    prior_cnt = (
        db.session.query(EmailVerificationToken)
        .filter(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.consumed_at.is_(None),
        )
        .update({"consumed_at": now}, synchronize_session=False)
    )
    raw_token = secrets.token_urlsafe(TOKEN_BYTES)
    expires_at = now + _ttl()
    row = EmailVerificationToken(
        user_id=user.id,
        email=user.email,
        token_sha256=_hash_token(raw_token),
        issued_at=now,
        expires_at=expires_at,
        issued_from_ip=ip,
    )
    db.session.add(row)
    _send_email(user, raw_token, expires_at)
    _emit_security_event(
        user,
        action="email.verification.issued",
        outcome="ok",
        details={"prior_revoked": int(prior_cnt), "email": user.email},
    )
    return IssueResult(user_id=user.id, raw_token=raw_token, expires_at=expires_at)


def consume(raw_token: str) -> User:
    """Validate, consume, and return the owning user.

    Marks the user ``email_verified=True``. Caller commits.
    """
    if not isinstance(raw_token, str) or len(raw_token) < 20 or len(raw_token) > 128:
        raise VerificationError("token_malformed")
    row = (
        db.session.query(EmailVerificationToken)
        .filter_by(token_sha256=_hash_token(raw_token))
        .one_or_none()
    )
    if row is None:
        raise VerificationError("token_unknown")
    if row.consumed_at is not None:
        raise VerificationError("token_consumed")
    now = datetime.utcnow()
    if row.expires_at < now:
        raise VerificationError("token_expired")
    user = db.session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise VerificationError("user_inactive")
    if user.email != row.email:
        # Email changed between issuance and consumption — refuse so
        # an attacker who captured the old-email token cannot verify
        # the new address.
        raise VerificationError("email_changed")
    row.consumed_at = now
    user.email_verified = True
    user.email_verified_at = now
    _emit_security_event(
        user, action="email.verification.consumed", outcome="ok",
        details={"email": user.email},
    )
    return user


def resend(user: User, *, ip: Optional[str] = None) -> IssueResult:
    """Same contract as ``issue``, kept distinct for call-site clarity."""
    return issue(user, ip=ip)


def _emit_security_event(
    user: User,
    *,
    action: str,
    outcome: str,
    details: Optional[dict] = None,
) -> None:
    import uuid

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
    verify_url = _verify_url(raw_token)
    display = user.first_name or user.username or user.email
    subject = "Verify your TrustSeal email address"
    text = (
        f"Hello {display},\n\n"
        "Please confirm this email address belongs to you by opening the "
        "link below. The link expires at "
        f"{expires_at.replace(microsecond=0).isoformat()} UTC.\n\n"
        f"{verify_url}\n\n"
        "If you did not create a TrustSeal account you can safely ignore "
        "this message — the link cannot be used without a registered "
        "account.\n\n"
        "— The TrustSeal team"
    )
    html = (
        "<p>Hello " + _html_escape(display) + ",</p>"
        "<p>Please confirm this email address belongs to you by opening "
        "the link below. The link expires at "
        + _html_escape(expires_at.replace(microsecond=0).isoformat())
        + " UTC.</p>"
        f'<p><a href="{_html_escape(verify_url)}">'
        f"{_html_escape(verify_url)}</a></p>"
        "<p>If you did not create a TrustSeal account you can safely ignore "
        "this message — the link cannot be used without a registered "
        "account.</p>"
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


def _html_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
