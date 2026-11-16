"""Scheduled reminder scanner (N2).

Finds prepared envelopes with active (not revoked, not consumed)
SignerInvitations whose owning participant has NOT acknowledged
yet, and sends a reminder email per participant via the mailer.

Dedup policy:

* ``last_reminder_at`` on ``SignerInvitation`` is updated on every
  successful send.
* A reminder is skipped for an invitation that received one within
  ``cooloff_hours`` (default 24).

Window policy:

* ``approaching_hours`` controls how close to ``expires_at`` the
  invitation must be before a reminder goes out. Defaults to 48
  hours, so recipients get two days of warning.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from app.extensions import db
from app.models.event_delivery import SecurityEvent
from app.models.signer_decision import SignerDecision
from app.models.signer_invitation import SignerInvitation
from app.models.signing_envelope import EnvelopeParticipant, SigningEnvelope
from app.models.user import User
from app.services import email as mailer


@dataclass(frozen=True)
class ReminderSent:
    invitation_id: int
    user_id: int
    envelope_id: int


DEFAULT_APPROACHING_HOURS = 48
DEFAULT_COOLOFF_HOURS = 24


def scan_reminders(
    *,
    approaching_hours: int = DEFAULT_APPROACHING_HOURS,
    cooloff_hours: int = DEFAULT_COOLOFF_HOURS,
    now: Optional[datetime] = None,
    base_url: Optional[str] = None,
) -> list[ReminderSent]:
    """Send a reminder per eligible participant and return the list."""
    moment = now or datetime.utcnow()
    approaching_window = moment + timedelta(hours=approaching_hours)
    cooloff_before = moment - timedelta(hours=cooloff_hours)
    base = (
        base_url
        or (
            __import__("flask").current_app.config.get("PUBLIC_BASE_URL")
            or ""
        ).rstrip("/")
    )
    candidates = (
        db.session.query(SignerInvitation, SigningEnvelope, EnvelopeParticipant, User)
        .join(
            SigningEnvelope,
            SignerInvitation.envelope_id == SigningEnvelope.id,
        )
        .join(
            EnvelopeParticipant,
            SignerInvitation.participant_id == EnvelopeParticipant.id,
        )
        .join(User, SignerInvitation.user_id == User.id)
        .filter(
            SignerInvitation.revoked_at.is_(None),
            SignerInvitation.consumed_at.is_(None),
            SignerInvitation.expires_at > moment,
            SignerInvitation.expires_at <= approaching_window,
            SigningEnvelope.state == "prepared",
            User.is_active.is_(True),
        )
        .all()
    )
    sent: list[ReminderSent] = []
    for invitation, envelope, participant, recipient in candidates:
        decided = (
            db.session.query(SignerDecision.id)
            .filter_by(
                envelope_id=envelope.id, participant_id=participant.id
            )
            .first()
        )
        if decided is not None:
            continue
        # Per-envelope reminder cadence override (Phase R1). NULL
        # columns fall back to the scanner's global defaults.
        effective_cooloff = (
            envelope.reminder_cooloff_hours
            if envelope.reminder_cooloff_hours is not None
            else cooloff_hours
        )
        this_cutoff = moment - timedelta(hours=effective_cooloff)
        if (
            invitation.last_reminder_at is not None
            and invitation.last_reminder_at > this_cutoff
        ):
            continue
        if (
            envelope.reminder_max_count is not None
            and invitation.reminder_count >= envelope.reminder_max_count
        ):
            continue
        _send(envelope, recipient, invitation, base)
        invitation.last_reminder_at = moment
        invitation.reminder_count = (invitation.reminder_count or 0) + 1
        db.session.add(
            SecurityEvent(
                organization_id=envelope.organization_id,
                actor_id=recipient.id,
                action="envelope.reminder.auto_sent",
                resource_type="signer_invitation",
                resource_id=invitation.id,
                outcome="ok",
                correlation_id=uuid.uuid4().hex,
            )
        )
        sent.append(
            ReminderSent(
                invitation_id=invitation.id,
                user_id=recipient.id,
                envelope_id=envelope.id,
            )
        )
    return sent


def _send(
    envelope: SigningEnvelope,
    recipient: User,
    invitation: SignerInvitation,
    base: str,
) -> None:
    sign_url = f"{base}/sign/envelope/{envelope.id}"
    hours_left = int(
        (invitation.expires_at - datetime.utcnow()).total_seconds() // 3600
    )
    subject = "Reminder: a document is waiting for your review"
    body = (
        f"Hello {recipient.first_name or recipient.username},\n\n"
        f"The envelope '{envelope.id}' is still waiting for your "
        f"acknowledgement. Your invitation expires in about "
        f"{max(hours_left, 0)} hours. Please visit:\n\n{sign_url}\n\n"
        "— The TrustSeal team"
    )
    mailer.send(
        mailer.EmailMessage(
            to=recipient.email, subject=subject, body_text=body
        )
    )
