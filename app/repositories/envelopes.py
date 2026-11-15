"""Envelope and participant repositories."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.signing_envelope import EnvelopeParticipant, SigningEnvelope
from .base import TenantScopedRepository


class EnvelopeRepository(TenantScopedRepository[SigningEnvelope]):
    model = SigningEnvelope
    tenant_column = "organization_id"

    def for_update(self, envelope_id: int) -> Optional[SigningEnvelope]:
        return (
            self._base()
            .filter(SigningEnvelope.id == envelope_id)
            .with_for_update()
            .first()
        )


class EnvelopeParticipantRepository:
    """Participants are scoped via their envelope; this repo always joins."""

    def __init__(self, session: Session, tenant_id: int) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def in_envelope(self, envelope_id: int) -> list[EnvelopeParticipant]:
        return (
            self._session.query(EnvelopeParticipant)
            .join(SigningEnvelope, SigningEnvelope.id == EnvelopeParticipant.envelope_id)
            .filter(
                SigningEnvelope.organization_id == self._tenant_id,
                EnvelopeParticipant.envelope_id == envelope_id,
            )
            .order_by(EnvelopeParticipant.signing_order)
            .all()
        )

    def find(self, envelope_id: int, participant_id: int) -> Optional[EnvelopeParticipant]:
        return (
            self._session.query(EnvelopeParticipant)
            .join(SigningEnvelope, SigningEnvelope.id == EnvelopeParticipant.envelope_id)
            .filter(
                SigningEnvelope.organization_id == self._tenant_id,
                SigningEnvelope.id == envelope_id,
                EnvelopeParticipant.id == participant_id,
            )
            .first()
        )
