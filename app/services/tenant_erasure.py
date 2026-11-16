"""GDPR Article 17 ("right to erasure") for individual users.

Scope: this service anonymises identifying information attached to
a single user while preserving the tamper-evident audit chain + the
evidence dossier for completed trust actions. The chain remains
verifiable because:

* We only overwrite PII fields (name, email, phone, username). The
  SHA-256 hash of the user id — not the email — is what the audit
  chain links against, so rotation of the row is safe.
* Documents / envelopes / decisions keep their references: the
  ``created_by_id`` column still points at the now-pseudonymised
  user. The evidence record remains legally defensible — only the
  real-world identity has been redacted.

Policy guards:

* A user with an active legal hold is refused with
  ``ErasureError("legal_hold_active")``.
* A user with non-terminal signer invitations is refused — complete
  or withdraw the invitation first.
* An admin cannot erase themselves. Separation-of-duties applies.

The pseudonym is a stable per-user hash (HMAC-SHA256 of the user id
under the operator's ``SECRET_KEY``), truncated to 16 hex chars.
Every erasure emits a chained SecurityEvent for the audit log.
"""
from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from flask import current_app

from app.extensions import db
from app.models.event_delivery import SecurityEvent
from app.models.evidence_preservation import EvidenceLegalHold
from app.models.signer_invitation import SignerInvitation
from app.models.user import User


class ErasureError(RuntimeError):
    """Policy or state failure during erasure."""


@dataclass(frozen=True)
class ErasureOutcome:
    user_id: int
    pseudonym: str
    erased_at: datetime


def _pseudonym(user_id: int) -> str:
    secret = current_app.config.get("SECRET_KEY") or ""
    if not secret:
        raise ErasureError("secret_key_not_configured")
    mac = hmac.new(
        secret.encode("utf-8"),
        f"user:{user_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return mac[:16]


def _has_active_legal_hold(user_id: int) -> bool:
    return (
        db.session.query(EvidenceLegalHold)
        .filter(
            EvidenceLegalHold.requested_by_id == user_id,
            EvidenceLegalHold.released_at.is_(None),
        )
        .count()
    ) > 0


def _has_open_invitations(user_id: int) -> bool:
    return (
        db.session.query(SignerInvitation)
        .filter(
            SignerInvitation.user_id == user_id,
            SignerInvitation.consumed_at.is_(None),
            SignerInvitation.revoked_at.is_(None),
        )
        .count()
    ) > 0


def erase_user(
    *,
    user_id: int,
    requested_by_id: int,
    reason: Optional[str] = None,
) -> ErasureOutcome:
    """Pseudonymise ``user_id``'s PII; preserve the audit chain."""
    if user_id == requested_by_id:
        raise ErasureError("self_erasure_forbidden")
    user = db.session.get(User, user_id)
    if user is None:
        raise ErasureError("user_not_found")
    if _has_active_legal_hold(user_id):
        raise ErasureError("legal_hold_active")
    if _has_open_invitations(user_id):
        raise ErasureError("open_invitations_present")
    pseudonym = _pseudonym(user_id)
    now = datetime.utcnow()
    user.username = f"erased-{pseudonym}"
    user.email = f"erased-{pseudonym}@redacted.invalid"
    user.first_name = None
    user.last_name = None
    user.phone = None
    user.is_active = False
    # Force a password rotation so stolen hashes become useless.
    user.set_password(uuid.uuid4().hex)
    db.session.add(
        SecurityEvent(
            organization_id=user.organization_id,
            actor_id=requested_by_id,
            action="user.erased",
            resource_type="user",
            resource_id=user.id,
            outcome="ok",
            correlation_id=uuid.uuid4().hex,
        )
    )
    db.session.flush()
    return ErasureOutcome(user_id=user_id, pseudonym=pseudonym, erased_at=now)
