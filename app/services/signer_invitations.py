"""Issue, resolve, consume, and revoke signer invitations.

A raw invitation token looks like ``trs_<url-safe-random-bytes>``.
Only its SHA-256 digest is stored. ``issue`` is called by the
preparation flow and returns the raw token once; ``resolve`` is called
by the ``/sign/<token>`` view and returns the invitation row plus the
envelope + participant — or raises :class:`InvitationError` for any
condition that must not reveal state to the caller (expired, consumed,
revoked, unknown).

The error messages intentionally funnel into a single "invitation
unavailable" external message. Internal logs retain the specific
reason.
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from app.extensions import db
from app.models.signer_invitation import SignerInvitation
from app.models.signing_envelope import EnvelopeParticipant, SigningEnvelope

TOKEN_PREFIX = "trs_"
TOKEN_BYTES = 32  # 256-bit entropy
DEFAULT_LIFETIME = timedelta(days=14)


class InvitationError(RuntimeError):
    """A signer invitation cannot be resolved for a specific reason.

    ``reason`` is one of ``unknown``, ``expired``, ``consumed``,
    ``revoked``, ``wrong_envelope_state``. The view returns a generic
    "unavailable" message so the raw reason is never disclosed to the
    network caller.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ResolvedInvitation:
    invitation: SignerInvitation
    envelope: SigningEnvelope
    participant: EnvelopeParticipant


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def generate_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(TOKEN_BYTES)


def issue(
    *,
    envelope: SigningEnvelope,
    participant: EnvelopeParticipant,
    issued_by_id: int,
    lifetime: timedelta | None = None,
) -> tuple[SignerInvitation, str]:
    """Mint a fresh invitation for ``participant`` on ``envelope``.

    Returns ``(row, raw_token)``; the caller delivers the token to the
    signer out-of-band. Raises :class:`InvitationError` if an
    invitation already exists for this participant — enforce one
    invitation per participant by revoking the previous row first.
    """
    if participant.envelope_id != envelope.id:
        raise InvitationError("participant_envelope_mismatch")
    existing = SignerInvitation.query.filter_by(
        envelope_id=envelope.id, participant_id=participant.id
    ).first()
    if existing is not None and existing.consumed_at is None and existing.revoked_at is None:
        raise InvitationError("already_outstanding")
    token = generate_token()
    now = datetime.utcnow()
    row = SignerInvitation(
        envelope_id=envelope.id,
        participant_id=participant.id,
        user_id=participant.user_id,
        token_hash=_hash_token(token),
        issued_by_id=issued_by_id,
        created_at=now,
        expires_at=now + (lifetime or DEFAULT_LIFETIME),
    )
    db.session.add(row)
    db.session.flush()
    return row, token


def resolve(token: str, *, now: datetime | None = None) -> ResolvedInvitation:
    """Look up an invitation by token and validate every precondition."""
    if not isinstance(token, str) or not token.startswith(TOKEN_PREFIX):
        raise InvitationError("unknown")
    if len(token) > len(TOKEN_PREFIX) + 128:
        raise InvitationError("unknown")
    row = SignerInvitation.query.filter_by(token_hash=_hash_token(token)).first()
    if row is None:
        raise InvitationError("unknown")
    moment = now or datetime.utcnow()
    if row.revoked_at is not None:
        raise InvitationError("revoked")
    if row.consumed_at is not None:
        raise InvitationError("consumed")
    if row.expires_at is not None and row.expires_at < moment:
        raise InvitationError("expired")
    envelope = db.session.get(SigningEnvelope, row.envelope_id)
    participant = db.session.get(EnvelopeParticipant, row.participant_id)
    if envelope is None or participant is None:
        raise InvitationError("unknown")
    if envelope.state not in {"prepared"}:
        raise InvitationError("wrong_envelope_state")
    return ResolvedInvitation(
        invitation=row, envelope=envelope, participant=participant
    )


def consume(invitation: SignerInvitation) -> None:
    """Mark the invitation used. Idempotent — repeated consumes are no-ops."""
    if invitation.consumed_at is not None:
        return
    invitation.consumed_at = datetime.utcnow()
    db.session.flush()


def revoke(
    invitation: SignerInvitation, *, reason: str, now: Optional[datetime] = None
) -> None:
    if invitation.revoked_at is not None:
        return
    invitation.revoked_at = now or datetime.utcnow()
    invitation.revoke_reason = reason[:80]
    db.session.flush()
