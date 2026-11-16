"""Scheduled envelope expiry.

Walks every prepared envelope with ``expires_at < now`` AND no
recorded ``SignerDecision``. Each matching envelope is withdrawn
with ``withdraw_reason='expired'`` so the lifecycle flag is
auditable later.

Envelopes with at least one decision are NOT auto-withdrawn —
they continue through the existing finalisation path. Operators
who need to end an envelope after decisions have landed call the
regular withdraw endpoint.

The caller commits.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.extensions import db
from app.models.event_delivery import SecurityEvent
from app.models.signer_decision import SignerDecision
from app.models.signing_envelope import SigningEnvelope


@dataclass(frozen=True)
class ExpiryOutcome:
    envelope_id: int
    expired_at: datetime


def cancel_expired_envelopes(
    *, now: Optional[datetime] = None, batch: int = 500
) -> list[ExpiryOutcome]:
    """Withdraw every prepared envelope whose expiry has passed.

    Returns the list of withdrawn envelopes. Idempotent — already
    withdrawn or cancelled envelopes are skipped.
    """
    moment = now or datetime.utcnow()
    candidates = (
        SigningEnvelope.query.filter(
            SigningEnvelope.state == "prepared",
            SigningEnvelope.expires_at.isnot(None),
            SigningEnvelope.expires_at < moment,
        )
        .order_by(SigningEnvelope.id.asc())
        .limit(batch)
        .all()
    )
    outcomes: list[ExpiryOutcome] = []
    for envelope in candidates:
        already_decided = (
            db.session.query(SignerDecision.id)
            .filter(SignerDecision.envelope_id == envelope.id)
            .first()
            is not None
        )
        if already_decided:
            # The regular finalization / withdraw path owns this one.
            continue
        envelope.state = "withdrawn"
        envelope.withdrawn_at = moment
        envelope.withdraw_reason = "expired"
        db.session.add(
            SecurityEvent(
                organization_id=envelope.organization_id,
                actor_id=envelope.created_by_id,
                action="envelope.auto_withdrawn.expired",
                resource_type="signing_envelope",
                resource_id=envelope.id,
                outcome="ok",
                correlation_id=uuid.uuid4().hex,
            )
        )
        outcomes.append(
            ExpiryOutcome(envelope_id=envelope.id, expired_at=moment)
        )
    return outcomes
