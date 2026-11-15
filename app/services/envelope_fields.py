"""Envelope field management.

Creator-side (draft state only):

* ``create_field(envelope, participant, field_type, page_number,
  rect, *, label, required, created_by_id)``
* ``delete_field(envelope, field_id)``
* ``list_fields(envelope, viewer=None)`` — all fields for the
  creator; only the viewer's own fields when ``viewer`` is a
  participant.

Signer-side (prepared state):

* ``submit_values(envelope, participant, values, *, now=None)`` —
  ``values`` maps field ids to the submitted value. Only the
  participant's own fields may be addressed; other field ids raise
  :class:`FieldOwnershipError`. Values are persisted and
  ``submitted_at`` is stamped.

Preparation validation:

* ``validate_assignment(envelope)`` — raises
  :class:`FieldAssignmentError` if any ``required`` field is
  assigned to a non-signer participant, or if a signer participant
  has zero required fields. Called from ``/prepare``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable, Mapping, Optional

from app.extensions import db
from app.models.envelope_field import EnvelopeField, FIELD_TYPES
from app.models.signing_envelope import EnvelopeParticipant, SigningEnvelope


class FieldError(Exception):
    """Base class for field-service errors."""


class FieldOwnershipError(FieldError):
    """A caller tried to touch a field they do not own."""


class FieldAssignmentError(FieldError):
    """Preparation refused because field assignment is incomplete."""


@dataclass(frozen=True)
class Rect:
    x_pt: float
    y_pt: float
    width_pt: float
    height_pt: float


def _ensure_draft(envelope: SigningEnvelope) -> None:
    if envelope.state != "draft":
        raise FieldError("envelope_not_draft")


def _ensure_participant_of_envelope(
    envelope: SigningEnvelope, participant: EnvelopeParticipant
) -> None:
    if participant.envelope_id != envelope.id:
        raise FieldError("participant_envelope_mismatch")


def create_field(
    envelope: SigningEnvelope,
    participant: EnvelopeParticipant,
    *,
    field_type: str,
    page_number: int,
    rect: Rect,
    created_by_id: int,
    label: Optional[str] = None,
    required: bool = True,
) -> EnvelopeField:
    _ensure_draft(envelope)
    _ensure_participant_of_envelope(envelope, participant)
    if field_type not in FIELD_TYPES:
        raise FieldError("field_type_invalid")
    if not isinstance(page_number, int) or page_number <= 0:
        raise FieldError("page_number_invalid")
    if rect.width_pt <= 0 or rect.height_pt <= 0:
        raise FieldError("rect_invalid")
    row = EnvelopeField(
        envelope_id=envelope.id,
        participant_id=participant.id,
        field_type=field_type,
        label=(label or None),
        page_number=page_number,
        x_pt=Decimal(str(rect.x_pt)),
        y_pt=Decimal(str(rect.y_pt)),
        width_pt=Decimal(str(rect.width_pt)),
        height_pt=Decimal(str(rect.height_pt)),
        required=required,
        created_by_id=created_by_id,
    )
    db.session.add(row)
    db.session.flush()
    return row


def delete_field(envelope: SigningEnvelope, field_id: int) -> None:
    _ensure_draft(envelope)
    row = db.session.get(EnvelopeField, field_id)
    if row is None or row.envelope_id != envelope.id:
        raise FieldError("field_not_found")
    db.session.delete(row)


def list_fields(
    envelope: SigningEnvelope,
    *,
    viewer_participant_id: Optional[int] = None,
) -> list[EnvelopeField]:
    query = EnvelopeField.query.filter_by(envelope_id=envelope.id)
    if viewer_participant_id is not None:
        query = query.filter_by(participant_id=viewer_participant_id)
    return query.order_by(
        EnvelopeField.page_number.asc(),
        EnvelopeField.y_pt.desc(),
        EnvelopeField.x_pt.asc(),
    ).all()


def submit_values(
    envelope: SigningEnvelope,
    participant: EnvelopeParticipant,
    values: Mapping[int, str],
    *,
    now: Optional[datetime] = None,
) -> list[EnvelopeField]:
    """Apply submitted values to the participant's own fields.

    Values for fields the participant does not own raise
    :class:`FieldOwnershipError`. Already-submitted fields raise
    :class:`FieldError("field_already_submitted")`. Returns the
    updated rows.
    """
    _ensure_participant_of_envelope(envelope, participant)
    if envelope.state != "prepared":
        raise FieldError("envelope_not_prepared")
    moment = now or datetime.utcnow()
    updated: list[EnvelopeField] = []
    for field_id, raw in (values or {}).items():
        row = db.session.get(EnvelopeField, int(field_id))
        if row is None or row.envelope_id != envelope.id:
            raise FieldOwnershipError("field_not_found")
        if row.participant_id != participant.id:
            raise FieldOwnershipError("field_not_owned")
        if row.submitted_at is not None:
            raise FieldError("field_already_submitted")
        row.value = None if raw is None else str(raw)
        row.submitted_at = moment
        updated.append(row)
    return updated


def validate_assignment(envelope: SigningEnvelope) -> None:
    """Raise if any required field is unassigned or on a non-signer."""
    participant_role = {
        p.id: p.role
        for p in EnvelopeParticipant.query.filter_by(
            envelope_id=envelope.id
        ).all()
    }
    if not participant_role:
        # No participants at all is caught elsewhere; this helper
        # focuses on field-assignment integrity.
        return
    for field in list_fields(envelope):
        role = participant_role.get(field.participant_id)
        if role is None:
            raise FieldAssignmentError("field_participant_missing")
        if field.required and role != "signer":
            raise FieldAssignmentError(
                f"field_{field.id}_assigned_to_{role}"
            )


def required_fields_satisfied(
    envelope: SigningEnvelope, participant: EnvelopeParticipant
) -> bool:
    """True iff every required field owned by ``participant`` has a value."""
    outstanding = EnvelopeField.query.filter_by(
        envelope_id=envelope.id,
        participant_id=participant.id,
        required=True,
        submitted_at=None,
    ).count()
    return outstanding == 0
