"""Authenticated envelope preparation; deliberately no signing endpoints.

Only the document owner can prepare an envelope. Participants must be active
members of the same tenant. Preparation locks the recipient list and the
previously scanned PDF digest; signer challenges/consent come later.
"""
from datetime import datetime
from flask import Blueprint, abort, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from app.extensions import db
from app.models.user import User
from app.models.documents.document import Document
from app.models.documents.document_blob import DocumentBlob
from app.models.signing_envelope import (
    EnvelopeLabel,
    EnvelopeParticipant,
    SigningEnvelope,
)
from app.services.token_security import active_token_user
from app.services.event_delivery import enqueue
from app.services.documents.private_storage import check_object_digest, IngestionError
from app.services.idempotency import idempotent
from app.services import envelope_fields as fields_service
from app.services.envelope_fields import Rect
from app.models.envelope_field import EnvelopeField

envelope_api = Blueprint("envelope_api", __name__, url_prefix="/api/envelopes")


def _actor():
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    if user.organization_id is None:
        abort(403)
    return user


def _owned(envelope_id, user, lock=False):
    query = SigningEnvelope.query.filter_by(
        id=envelope_id, organization_id=user.organization_id, created_by_id=user.id
    )
    item = (query.with_for_update() if lock else query).first()
    if item is None:
        abort(404)
    return item


def _payload():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        abort(400, description="JSON object required")
    return value


def _details(item):
    people = EnvelopeParticipant.query.filter_by(envelope_id=item.id).order_by(
        EnvelopeParticipant.signing_order
    ).all()
    labels = sorted(
        row.label
        for row in EnvelopeLabel.query.filter_by(envelope_id=item.id).all()
    )
    return {
        "labels": labels,
        "id": item.id, "document_id": item.document_id,
        "document_blob_id": item.document_blob_id,
        "document_sha256": item.document_sha256,
        "state": item.state, "created_by_id": item.created_by_id,
        "routing_mode": item.routing_mode,
        "quorum_required": item.quorum_required,
        "preview_confirmed_at": item.preview_confirmed_at.isoformat()
        if item.preview_confirmed_at
        else None,
        "withdrawn_at": item.withdrawn_at.isoformat()
        if item.withdrawn_at
        else None,
        "withdrawn_by_id": item.withdrawn_by_id,
        "withdraw_reason": item.withdraw_reason,
        "supersedes_envelope_id": item.supersedes_envelope_id,
        "superseded_by_envelope_id": item.superseded_by_envelope_id,
        "expires_at": item.expires_at.isoformat() if item.expires_at else None,
        "reminder_cooloff_hours": item.reminder_cooloff_hours,
        "reminder_max_count": item.reminder_max_count,
        "archived_at": item.archived_at.isoformat() if item.archived_at else None,
        "archived_by_id": item.archived_by_id,
        "participants": [
            {"id": p.id, "user_id": p.user_id, "role": p.role,
             "signing_order": p.signing_order} for p in people
        ],
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "prepared_at": item.prepared_at.isoformat() if item.prepared_at else None,
        "cancelled_at": item.cancelled_at.isoformat() if item.cancelled_at else None,
        "assurance": "preparation_only_not_signed",
    }


@envelope_api.route("", methods=["POST"])
@jwt_required()
def create_envelope():
    user = _actor()
    data = _payload()
    extra = set(data) - {
        "document_id",
        "document_blob_id",
        "routing_mode",
        "quorum_required",
        "expires_at",
    }
    if extra or "document_id" not in data or "document_blob_id" not in data:
        abort(400, description="document_id and document_blob_id required")
    document_id, blob_id = data["document_id"], data["document_blob_id"]
    if type(document_id) is not int or type(blob_id) is not int:
        abort(400)
    routing_mode = data.get("routing_mode", "sequential")
    if routing_mode not in ("sequential", "parallel", "quorum"):
        abort(400, description="routing_mode must be sequential|parallel|quorum")
    quorum_required = data.get("quorum_required")
    if routing_mode == "quorum":
        if not isinstance(quorum_required, int) or quorum_required < 1:
            abort(400, description="quorum_required must be positive integer")
    else:
        if quorum_required is not None:
            abort(400, description="quorum_required only valid for quorum mode")
    doc = Document.query.filter_by(
        id=document_id, created_by=user.id,
        organization_id=user.organization_id, deleted_at=None
    ).first()
    if doc is None:
        abort(404)
    if (doc.status or "").lower() not in {"draft", "pending"}:
        abort(409, description="Document is not eligible for preparation")
    blob = DocumentBlob.query.filter_by(id=blob_id, document_id=doc.id).first()
    if blob is None:
        abort(404)
    try:
        check_object_digest(blob.object_key, blob.sha256, current_app.config)
    except IngestionError:
        abort(503, description="Stored document integrity unavailable")
    expires_at_raw = data.get("expires_at")
    expires_at = None
    if expires_at_raw is not None:
        if not isinstance(expires_at_raw, str):
            abort(400, description="expires_at_must_be_iso_string")
        try:
            expires_at = datetime.fromisoformat(expires_at_raw)
        except ValueError:
            abort(400, description="expires_at_invalid_iso")
        if expires_at <= datetime.utcnow():
            abort(400, description="expires_at_must_be_future")
    envelope = SigningEnvelope(
        document_id=doc.id, document_blob_id=blob.id,
        document_sha256=blob.sha256, organization_id=user.organization_id,
        created_by_id=user.id, state="draft",
        routing_mode=routing_mode,
        quorum_required=quorum_required,
        expires_at=expires_at,
    )
    db.session.add(envelope)
    db.session.flush()
    enqueue(
        event_type="envelope.draft.created", aggregate_type="envelope",
        aggregate_id=envelope.id, organization_id=user.organization_id,
        actor_id=user.id, action="envelope.draft.created",
        idempotency_key="envelope-created:%s" % envelope.id,
    )
    db.session.commit()
    return jsonify(_details(envelope)), 201


@envelope_api.route("", methods=["GET"])
@jwt_required()
def list_envelopes():
    user = _actor()
    query = SigningEnvelope.query.filter_by(
        created_by_id=user.id, organization_id=user.organization_id
    )
    label_filter = request.args.get("label")
    if label_filter:
        query = query.join(
            EnvelopeLabel,
            EnvelopeLabel.envelope_id == SigningEnvelope.id,
        ).filter(EnvelopeLabel.label == label_filter)
    if request.args.get("include_archived") != "1":
        query = query.filter(SigningEnvelope.archived_at.is_(None))
    items = query.order_by(SigningEnvelope.id.desc()).limit(100).all()
    return jsonify([_details(item) for item in items])


@envelope_api.route("/<int:envelope_id>", methods=["GET"])
@jwt_required()
def get_envelope(envelope_id):
    return jsonify(_details(_owned(envelope_id, _actor())))


@envelope_api.route("/<int:envelope_id>/participants", methods=["POST"])
@jwt_required()
def add_participant(envelope_id):
    user = _actor()
    envelope = _owned(envelope_id, user, lock=True)
    if envelope.state != "draft":
        abort(409, description="Recipient list is locked")
    data = _payload()
    if set(data) != {"user_id", "signing_order"}:
        abort(400, description="user_id and signing_order required")
    recipient_id, order = data["user_id"], data["signing_order"]
    if type(recipient_id) is not int or type(order) is not int or order < 1:
        abort(400)
    recipient = db.session.get(User, recipient_id)
    if recipient is None or not recipient.is_active or recipient.organization_id != user.organization_id:
        abort(404, description="Active recipient not found in organisation")
    existing = EnvelopeParticipant.query.filter_by(envelope_id=envelope.id).all()
    if any(p.user_id == recipient_id or p.signing_order == order for p in existing):
        abort(409, description="Duplicate recipient or signing order")
    db.session.add(EnvelopeParticipant(
        envelope_id=envelope.id, user_id=recipient_id,
        signing_order=order, role="signer",
    ))
    db.session.commit()
    return jsonify(_details(envelope)), 201


@envelope_api.route(
    "/<int:envelope_id>/participants/bulk", methods=["POST"]
)
@jwt_required()
def bulk_add_participants(envelope_id):
    """Atomically add a batch of participants to a draft envelope.

    Payload: ``{"participants": [{"user_id": int, "signing_order": int,
    "role": "signer"|"witness"}, ...]}``. Per-row failures are reported
    in the response without touching successful rows — the service
    runs a savepoint per row so one bad entry does not reject the
    batch. Successful rows are only committed if the whole batch
    produces at least one success (otherwise the envelope is left
    untouched).
    """
    user = _actor()
    envelope = _owned(envelope_id, user, lock=True)
    if envelope.state != "draft":
        abort(409, description="Recipient list is locked")
    data = _payload()
    rows = data.get("participants")
    if not isinstance(rows, list) or not rows:
        abort(400, description="participants_list_required")
    if len(rows) > 100:
        abort(413, description="bulk_participants_limit_100")

    existing = EnvelopeParticipant.query.filter_by(
        envelope_id=envelope.id
    ).all()
    seen_users = {p.user_id for p in existing}
    seen_orders = {p.signing_order for p in existing}
    results: list[dict] = []
    added: list[EnvelopeParticipant] = []
    for idx, row in enumerate(rows):
        entry = {"index": idx}
        if not isinstance(row, dict):
            entry["status"] = "failed"
            entry["error_code"] = "row_not_object"
            results.append(entry)
            continue
        recipient_id = row.get("user_id")
        order = row.get("signing_order")
        role = row.get("role", "signer")
        if type(recipient_id) is not int or type(order) is not int or order < 1:
            entry["status"] = "failed"
            entry["error_code"] = "fields_invalid"
            results.append(entry)
            continue
        if role not in ("signer", "witness"):
            entry["status"] = "failed"
            entry["error_code"] = "role_invalid"
            results.append(entry)
            continue
        if recipient_id in seen_users:
            entry["status"] = "failed"
            entry["error_code"] = "duplicate_user"
            results.append(entry)
            continue
        if order in seen_orders:
            entry["status"] = "failed"
            entry["error_code"] = "duplicate_signing_order"
            results.append(entry)
            continue
        recipient = db.session.get(User, recipient_id)
        if (
            recipient is None
            or not recipient.is_active
            or recipient.organization_id != user.organization_id
        ):
            entry["status"] = "failed"
            entry["error_code"] = "recipient_not_found"
            results.append(entry)
            continue
        new_row = EnvelopeParticipant(
            envelope_id=envelope.id,
            user_id=recipient_id,
            signing_order=order,
            role=role,
        )
        db.session.add(new_row)
        db.session.flush()
        added.append(new_row)
        seen_users.add(recipient_id)
        seen_orders.add(order)
        entry["status"] = "succeeded"
        entry["participant_id"] = new_row.id
        entry["user_id"] = recipient_id
        entry["signing_order"] = order
        entry["role"] = role
        results.append(entry)

    if not added:
        db.session.rollback()
        return (
            jsonify(
                envelope_id=envelope.id,
                added=0,
                failed=len(rows),
                results=results,
            ),
            400,
        )
    db.session.commit()
    http_status = 207 if any(r["status"] == "failed" for r in results) else 201
    return (
        jsonify(
            envelope_id=envelope.id,
            added=len(added),
            failed=len(rows) - len(added),
            results=results,
        ),
        http_status,
    )


def valid_signing_order(orders):
    """Signing positions must be contiguous and unambiguous."""
    return bool(orders) and all(type(value) is int for value in orders) and (
        sorted(orders) == list(range(1, len(orders) + 1))
    )


@envelope_api.route("/<int:envelope_id>/prepare", methods=["POST"])
@jwt_required()
@idempotent("envelopes.prepare")
def prepare_envelope(envelope_id):
    from app.policies.step_up_enforcement import enforce as _enforce_step_up
    _enforce_step_up()
    user = _actor()
    envelope = _owned(envelope_id, user, lock=True)
    if envelope.state != "draft":
        abort(409, description="Envelope is no longer editable")
    # Entitlement check: if the tenant's plan caps envelope.prepared
    # hits for the period, refuse before locking the envelope state.
    from app.services import entitlements as _entitlements

    try:
        _entitlements.check(user.organization_id, "envelope.prepared")
    except _entitlements.EntitlementExceeded as exc:
        return (
            jsonify(
                error=str(exc),
                meter=exc.meter,
                period=exc.period,
                used=exc.used,
                limit=exc.limit,
                type="https://trustseal.dev/problems/entitlement-exceeded",
            ),
            402,
        )
    participants = EnvelopeParticipant.query.filter_by(
        envelope_id=envelope.id
    ).order_by(EnvelopeParticipant.signing_order).all()
    if not valid_signing_order([p.signing_order for p in participants]):
        abort(409, description="Continuous signing order from 1 required")
    active_recipients = User.query.filter(
        User.id.in_([p.user_id for p in participants]),
        User.organization_id == user.organization_id,
        User.is_active.is_(True),
    ).count()
    if active_recipients != len(participants):
        abort(409, description="A recipient is no longer active in this organisation")
    # Preview checkpoint: refuse to leave draft unless the creator
    # has acknowledged the preview snapshot. The confirm endpoint
    # stamps preview_confirmed_at; prepare rejects until it's set.
    if envelope.preview_confirmed_at is None:
        abort(
            409,
            description="preview_confirmation_required",
        )
    # Quorum-mode envelopes must demand at least one and at most N
    # acknowledgements where N is the number of signer (non-witness)
    # participants.
    if envelope.routing_mode == "quorum":
        signer_count = sum(1 for p in participants if p.role == "signer")
        if (
            envelope.quorum_required is None
            or envelope.quorum_required < 1
            or envelope.quorum_required > signer_count
        ):
            abort(409, description="quorum_required_out_of_range")
    try:
        fields_service.validate_assignment(envelope)
    except fields_service.FieldAssignmentError as exc:
        abort(409, description=str(exc))
    doc = Document.query.filter_by(
        id=envelope.document_id, created_by=user.id,
        organization_id=user.organization_id, deleted_at=None
    ).with_for_update().first()
    if doc is None or (doc.status or "").lower() not in {"draft", "pending"}:
        abort(409, description="Source document is unavailable")
    blob = db.session.get(DocumentBlob, envelope.document_blob_id)
    if blob is None or blob.document_id != doc.id or blob.sha256 != envelope.document_sha256:
        abort(409, description="Source manifest has changed")
    try:
        check_object_digest(blob.object_key, blob.sha256, current_app.config)
    except IngestionError:
        abort(503, description="Source PDF integrity check failed")
    envelope.state = "prepared"
    envelope.prepared_at = datetime.utcnow()
    enqueue(
        event_type="envelope.prepared", aggregate_type="envelope",
        aggregate_id=envelope.id, organization_id=user.organization_id,
        actor_id=user.id, action="envelope.prepared",
        idempotency_key="envelope-prepared:%s" % envelope.id,
    )
    # Meter the business event with the envelope id so retries
    # (idempotent prepare) never double-count.
    from app.services import usage_ledger as _usage

    _usage.record(
        user.organization_id,
        "envelope.prepared",
        f"envelope:{envelope.id}",
        actor_id=user.id,
    )
    db.session.commit()
    return jsonify(_details(envelope))


@envelope_api.route("/<int:envelope_id>/cancel", methods=["POST"])
@jwt_required()
@idempotent("envelopes.cancel")
def cancel_envelope(envelope_id):
    user = _actor()
    envelope = _owned(envelope_id, user, lock=True)
    if envelope.state == "cancelled":
        return jsonify(_details(envelope))
    from app.models.pdf_finalization import FinalizedPdf
    if FinalizedPdf.query.filter_by(envelope_id=envelope.id).first() is not None:
        abort(409, description="Finalized PDF cannot be cancelled")
    if envelope.state not in ("draft", "prepared"):
        abort(409)
    envelope.state = "cancelled"
    envelope.cancelled_at = datetime.utcnow()
    enqueue(
        event_type="envelope.cancelled", aggregate_type="envelope",
        aggregate_id=envelope.id, organization_id=user.organization_id,
        actor_id=user.id, action="envelope.cancelled",
        idempotency_key="envelope-cancelled:%s" % envelope.id,
    )
    db.session.commit()
    return jsonify(_details(envelope))


# --------------------------------------------------------------- fields


def _field_dict(row: EnvelopeField) -> dict:
    return {
        "id": row.id,
        "participant_id": row.participant_id,
        "field_type": row.field_type,
        "label": row.label,
        "page_number": row.page_number,
        "x_pt": float(row.x_pt),
        "y_pt": float(row.y_pt),
        "width_pt": float(row.width_pt),
        "height_pt": float(row.height_pt),
        "required": row.required,
        "value": row.value,
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
    }


# --------------------------------------------------------------- I6 lineage


@envelope_api.route("/<int:envelope_id>/lineage", methods=["GET"])
@jwt_required()
def envelope_lineage(envelope_id):
    """Return the full supersession chain for the envelope.

    Walks backwards along ``supersedes_envelope_id`` and forwards
    along ``superseded_by_envelope_id`` so the verification UI can
    render every related envelope in creation order with its state
    + prepared_at + sealed_pdf_sha256 (when one exists).
    """
    user = _actor()
    envelope = _owned(envelope_id, user)

    seen: set[int] = set()

    def _walk_back(start):
        chain = []
        current = start
        while current is not None and current.id not in seen:
            seen.add(current.id)
            chain.append(current)
            if current.supersedes_envelope_id is None:
                break
            current = db.session.get(
                SigningEnvelope, current.supersedes_envelope_id
            )
            if current is None or current.organization_id != user.organization_id:
                break
        chain.reverse()
        return chain

    def _walk_forward(start):
        chain = []
        current = start
        while current is not None:
            if current.superseded_by_envelope_id is None:
                break
            nxt = db.session.get(
                SigningEnvelope, current.superseded_by_envelope_id
            )
            if (
                nxt is None
                or nxt.organization_id != user.organization_id
                or nxt.id in seen
            ):
                break
            seen.add(nxt.id)
            chain.append(nxt)
            current = nxt
        return chain

    back = _walk_back(envelope)
    forward = _walk_forward(envelope)
    full = back + forward
    from app.models.pdf_finalization import FinalizedPdf

    def _sealed_sha(env_id):
        row = (
            FinalizedPdf.query.filter_by(envelope_id=env_id)
            .order_by(FinalizedPdf.id.desc())
            .first()
        )
        return row.output_sha256 if row is not None else None

    return jsonify(
        current_envelope_id=envelope.id,
        chain=[
            {
                "id": item.id,
                "state": item.state,
                "routing_mode": item.routing_mode,
                "prepared_at": item.prepared_at.isoformat()
                if item.prepared_at
                else None,
                "withdrawn_at": item.withdrawn_at.isoformat()
                if item.withdrawn_at
                else None,
                "cancelled_at": item.cancelled_at.isoformat()
                if item.cancelled_at
                else None,
                "sealed_pdf_sha256": _sealed_sha(item.id),
                "supersedes_envelope_id": item.supersedes_envelope_id,
                "superseded_by_envelope_id": item.superseded_by_envelope_id,
                "is_current": item.id == envelope.id,
            }
            for item in full
        ],
    )


# --------------------------------------------------------------- H1 rules


@envelope_api.route(
    "/<int:envelope_id>/participants/<int:participant_id>/rules",
    methods=["POST"],
)
@jwt_required()
def add_participant_rule(envelope_id, participant_id):
    """Attach a conditional routing rule to a participant (draft only)."""
    from app.services import envelope_routing_rules

    user = _actor()
    envelope = _owned(envelope_id, user, lock=True)
    participant = db.session.get(EnvelopeParticipant, participant_id)
    if participant is None or participant.envelope_id != envelope.id:
        abort(404)
    data = _payload()
    name = data.get("name")
    predicate = data.get("predicate")
    if not isinstance(name, str) or not isinstance(predicate, dict):
        abort(400, description="name_and_predicate_required")
    try:
        row = envelope_routing_rules.add_rule(
            envelope,
            participant,
            name=name,
            predicate=predicate,
            created_by_id=user.id,
        )
    except envelope_routing_rules.RuleError as exc:
        db.session.rollback()
        abort(400, description=str(exc))
    db.session.commit()
    return (
        jsonify(
            id=row.id,
            envelope_id=row.envelope_id,
            participant_id=row.participant_id,
            name=row.name,
            predicate=row.predicate,
        ),
        201,
    )


@envelope_api.route(
    "/<int:envelope_id>/rules/<int:rule_id>", methods=["DELETE"]
)
@jwt_required()
def delete_participant_rule(envelope_id, rule_id):
    from app.services import envelope_routing_rules

    user = _actor()
    envelope = _owned(envelope_id, user, lock=True)
    try:
        envelope_routing_rules.delete_rule(envelope, rule_id)
    except envelope_routing_rules.RuleError as exc:
        db.session.rollback()
        abort(404, description=str(exc))
    db.session.commit()
    return jsonify(message="rule_deleted"), 200


@envelope_api.route("/<int:envelope_id>/rules", methods=["GET"])
@jwt_required()
def list_participant_rules(envelope_id):
    from app.services import envelope_routing_rules

    user = _actor()
    envelope = _owned(envelope_id, user)
    rows = envelope_routing_rules.list_rules(envelope)
    return jsonify(
        rules=[
            {
                "id": r.id,
                "participant_id": r.participant_id,
                "name": r.name,
                "predicate": r.predicate,
            }
            for r in rows
        ]
    )


# --------------------------------------------------------------- F3 reissue


@envelope_api.route("/<int:envelope_id>/reissue", methods=["POST"])
@jwt_required()
@idempotent("envelopes.reissue")
def reissue_envelope(envelope_id):
    """Clone a prepared / withdrawn / cancelled envelope into a fresh draft.

    Preserves lineage: the new envelope's ``supersedes_envelope_id``
    points back at the original; the original's
    ``superseded_by_envelope_id`` points forward at the new one and
    its state flips to ``superseded`` (if not already terminal). All
    participants + fields are copied so the caller can edit the new
    draft before confirming its preview and preparing.
    """
    user = _actor()
    original = _owned(envelope_id, user, lock=True)
    if original.state not in ("prepared", "withdrawn", "cancelled"):
        abort(409, description="reissue_requires_terminal_state")
    if original.superseded_by_envelope_id is not None:
        abort(409, description="envelope_already_superseded")

    clone = SigningEnvelope(
        organization_id=original.organization_id,
        document_id=original.document_id,
        document_blob_id=original.document_blob_id,
        document_sha256=original.document_sha256,
        created_by_id=user.id,
        state="draft",
        routing_mode=original.routing_mode,
        quorum_required=original.quorum_required,
        supersedes_envelope_id=original.id,
    )
    db.session.add(clone)
    db.session.flush()

    # Copy participants.
    participants_old = EnvelopeParticipant.query.filter_by(
        envelope_id=original.id
    ).order_by(EnvelopeParticipant.signing_order.asc()).all()
    old_to_new: dict[int, int] = {}
    for p in participants_old:
        new_p = EnvelopeParticipant(
            envelope_id=clone.id,
            user_id=p.user_id,
            signing_order=p.signing_order,
            role=p.role,
        )
        db.session.add(new_p)
        db.session.flush()
        old_to_new[p.id] = new_p.id

    # Copy fields with freshly-mapped participant ids and no values.
    for f in EnvelopeField.query.filter_by(envelope_id=original.id).all():
        db.session.add(
            EnvelopeField(
                envelope_id=clone.id,
                participant_id=old_to_new[f.participant_id],
                field_type=f.field_type,
                label=f.label,
                page_number=f.page_number,
                x_pt=f.x_pt,
                y_pt=f.y_pt,
                width_pt=f.width_pt,
                height_pt=f.height_pt,
                required=f.required,
                created_by_id=user.id,
            )
        )

    # Mark the original superseded (unless it's withdrawn/cancelled,
    # which are terminal and keep their state but still record the
    # forward pointer).
    original.superseded_by_envelope_id = clone.id
    if original.state == "prepared":
        original.state = "superseded"

    enqueue(
        event_type="envelope.reissued", aggregate_type="envelope",
        aggregate_id=clone.id, organization_id=user.organization_id,
        actor_id=user.id, action="envelope.reissued",
        idempotency_key="envelope-reissued:%s" % clone.id,
    )
    db.session.commit()
    return jsonify(_details(clone)), 201


# --------------------------------------------------------------- C4/C5 extras


@envelope_api.route("/<int:envelope_id>/preview", methods=["GET"])
@jwt_required()
def preview_envelope(envelope_id):
    """Return a creator-side snapshot used to confirm before prepare.

    Includes participants, field count, routing mode + quorum info,
    and the current preview-confirmed timestamp so the UI can render
    a diff between confirmed and current state. The caller must still
    hit ``/preview/confirm`` before ``/prepare`` will succeed.
    """
    user = _actor()
    envelope = _owned(envelope_id, user)
    participants = EnvelopeParticipant.query.filter_by(
        envelope_id=envelope.id
    ).order_by(EnvelopeParticipant.signing_order).all()
    fields = EnvelopeField.query.filter_by(envelope_id=envelope.id).all()
    return jsonify(
        envelope=_details(envelope),
        field_count=len(fields),
        required_field_count=sum(1 for f in fields if f.required),
        participants_by_role={
            "signer": sum(1 for p in participants if p.role == "signer"),
            "witness": sum(1 for p in participants if p.role == "witness"),
        },
    )


@envelope_api.route("/<int:envelope_id>/preview/confirm", methods=["POST"])
@jwt_required()
@idempotent("envelopes.preview.confirm")
def confirm_preview(envelope_id):
    user = _actor()
    envelope = _owned(envelope_id, user, lock=True)
    if envelope.state != "draft":
        abort(409, description="preview_only_from_draft")
    envelope.preview_confirmed_at = datetime.utcnow()
    db.session.commit()
    return jsonify(_details(envelope)), 200


@envelope_api.route("/<int:envelope_id>/withdraw", methods=["POST"])
@jwt_required()
@idempotent("envelopes.withdraw")
def withdraw_envelope(envelope_id):
    """Withdraw a prepared envelope before any participant decides.

    Once any participant has acknowledged, the envelope moves through
    the regular finalization flow. Withdraw targets envelopes that
    have not yet gathered any decisions.
    """
    from app.models.signer_decision import SignerDecision

    user = _actor()
    envelope = _owned(envelope_id, user, lock=True)
    if envelope.state != "prepared":
        abort(409, description="withdraw_requires_prepared_state")
    existing = (
        SignerDecision.query.filter_by(envelope_id=envelope.id).count()
    )
    if existing:
        abort(409, description="withdraw_blocked_decisions_recorded")
    data = _payload() if request.data else {}
    reason = data.get("reason") if isinstance(data, dict) else None
    envelope.state = "withdrawn"
    envelope.withdrawn_at = datetime.utcnow()
    envelope.withdrawn_by_id = user.id
    envelope.withdraw_reason = (reason or None)
    enqueue(
        event_type="envelope.withdrawn", aggregate_type="envelope",
        aggregate_id=envelope.id, organization_id=user.organization_id,
        actor_id=user.id, action="envelope.withdrawn",
        idempotency_key="envelope-withdrawn:%s" % envelope.id,
    )
    db.session.commit()
    return jsonify(_details(envelope)), 200


@envelope_api.route("/bulk/withdraw", methods=["POST"])
@jwt_required()
def bulk_withdraw_envelopes():
    """Withdraw a batch of prepared envelopes in one call.

    Payload: ``{"envelope_ids": [int, ...], "reason": "..."}``.
    Each envelope is evaluated independently with the same guards
    as the single-envelope withdraw: the caller must own the row,
    the row must be in ``prepared`` state, and no participant
    decision may have been recorded. A row-level failure reports
    an ``error_code`` but does not reject the batch — successful
    rows are committed together. If **every** row fails the whole
    transaction rolls back.
    """
    from app.models.signer_decision import SignerDecision

    user = _actor()
    data = _payload()
    ids = data.get("envelope_ids")
    reason = data.get("reason")
    if not isinstance(ids, list) or not ids:
        abort(400, description="envelope_ids_required")
    if len(ids) > 100:
        abort(413, description="bulk_withdraw_limit_100")
    if reason is not None and not isinstance(reason, str):
        abort(400, description="reason_must_be_string")
    if reason is not None and len(reason) > 255:
        abort(400, description="reason_too_long")
    seen: set[int] = set()
    results: list[dict] = []
    withdrawn_count = 0
    for env_id in ids:
        entry = {"envelope_id": env_id}
        if type(env_id) is not int:
            entry["status"] = "failed"
            entry["error_code"] = "envelope_id_invalid"
            results.append(entry)
            continue
        if env_id in seen:
            entry["status"] = "failed"
            entry["error_code"] = "duplicate_id"
            results.append(entry)
            continue
        seen.add(env_id)
        envelope = (
            SigningEnvelope.query.filter_by(
                id=env_id,
                organization_id=user.organization_id,
                created_by_id=user.id,
            )
            .with_for_update()
            .first()
        )
        if envelope is None:
            entry["status"] = "failed"
            entry["error_code"] = "envelope_not_found"
            results.append(entry)
            continue
        if envelope.state != "prepared":
            entry["status"] = "failed"
            entry["error_code"] = "state_not_prepared"
            results.append(entry)
            continue
        if SignerDecision.query.filter_by(envelope_id=envelope.id).count():
            entry["status"] = "failed"
            entry["error_code"] = "decisions_recorded"
            results.append(entry)
            continue
        envelope.state = "withdrawn"
        envelope.withdrawn_at = datetime.utcnow()
        envelope.withdrawn_by_id = user.id
        envelope.withdraw_reason = reason or None
        enqueue(
            event_type="envelope.withdrawn",
            aggregate_type="envelope",
            aggregate_id=envelope.id,
            organization_id=user.organization_id,
            actor_id=user.id,
            action="envelope.withdrawn",
            idempotency_key="envelope-withdrawn:%s" % envelope.id,
        )
        withdrawn_count += 1
        entry["status"] = "succeeded"
        results.append(entry)
    if withdrawn_count == 0:
        db.session.rollback()
        return (
            jsonify(
                withdrawn=0,
                failed=len(results),
                results=results,
            ),
            400,
        )
    db.session.commit()
    http_status = 207 if withdrawn_count != len(results) else 200
    return (
        jsonify(
            withdrawn=withdrawn_count,
            failed=len(results) - withdrawn_count,
            results=results,
        ),
        http_status,
    )


@envelope_api.route(
    "/<int:envelope_id>/participants/<int:participant_id>/reminder",
    methods=["POST"],
)
@jwt_required()
def send_reminder(envelope_id, participant_id):
    """Send a reminder email to an unacknowledged participant."""
    from app.models.signer_decision import SignerDecision
    from app.services import email as mailer

    user = _actor()
    envelope = _owned(envelope_id, user)
    participant = db.session.get(EnvelopeParticipant, participant_id)
    if participant is None or participant.envelope_id != envelope.id:
        abort(404)
    if envelope.state != "prepared":
        abort(409, description="reminder_only_for_prepared")
    decided = SignerDecision.query.filter_by(
        envelope_id=envelope.id, participant_id=participant.id
    ).count()
    if decided:
        abort(409, description="participant_already_decided")
    recipient = db.session.get(User, participant.user_id)
    if recipient is None or not recipient.is_active:
        abort(404, description="recipient_inactive")
    base = (current_app.config.get("PUBLIC_BASE_URL") or "").rstrip("/")
    sign_url = f"{base}/sign/envelope/{envelope.id}"
    subject = "Reminder: a document is waiting for your review"
    body = (
        f"Hello {recipient.first_name or recipient.username},\n\n"
        f"The envelope '{envelope.id}' is waiting for your review and "
        f"acknowledgement. Please visit:\n\n{sign_url}\n\n"
        "— The TrustSeal team"
    )
    mailer.send(
        mailer.EmailMessage(
            to=recipient.email, subject=subject, body_text=body
        )
    )
    enqueue(
        event_type="envelope.reminder.sent", aggregate_type="envelope",
        aggregate_id=envelope.id, organization_id=user.organization_id,
        actor_id=user.id, action="envelope.reminder.sent",
        idempotency_key="envelope-reminder:%s:%s" % (envelope.id, participant.id),
    )
    db.session.commit()
    return jsonify(message="reminder_sent"), 200


@envelope_api.route(
    "/<int:envelope_id>/participants/<int:participant_id>/resend-invitation",
    methods=["POST"],
)
@jwt_required()
def resend_invitation(envelope_id, participant_id):
    """Revoke the outstanding signer invitation and issue a fresh one."""
    from app.models.signer_invitation import SignerInvitation
    from app.services import signer_invitations

    user = _actor()
    envelope = _owned(envelope_id, user)
    participant = db.session.get(EnvelopeParticipant, participant_id)
    if participant is None or participant.envelope_id != envelope.id:
        abort(404)
    if envelope.state != "prepared":
        abort(409, description="resend_requires_prepared_state")
    # Revoke any active invitation first.
    active = SignerInvitation.query.filter_by(
        envelope_id=envelope.id,
        participant_id=participant.id,
        revoked_at=None,
        consumed_at=None,
    ).all()
    for row in active:
        signer_invitations.revoke(row, reason="resend")
    _row, token = signer_invitations.issue(
        envelope=envelope,
        participant=participant,
        issued_by_id=user.id,
    )
    enqueue(
        event_type="envelope.invitation.resent", aggregate_type="envelope",
        aggregate_id=envelope.id, organization_id=user.organization_id,
        actor_id=user.id, action="envelope.invitation.resent",
        idempotency_key="envelope-invitation-resend:%s:%s" % (envelope.id, participant.id),
    )
    db.session.commit()
    return jsonify(message="invitation_resent", token=token), 200


@envelope_api.route("/<int:envelope_id>/fields", methods=["GET"])
@jwt_required()
def list_envelope_fields(envelope_id):
    """Return every field on the envelope (creator-only view)."""
    user = _actor()
    envelope = _owned(envelope_id, user)
    rows = fields_service.list_fields(envelope)
    return jsonify(fields=[_field_dict(r) for r in rows])


@envelope_api.route("/<int:envelope_id>/fields", methods=["POST"])
@jwt_required()
def add_envelope_field(envelope_id):
    """Add a field to the envelope (draft state only)."""
    user = _actor()
    envelope = _owned(envelope_id, user, lock=True)
    data = _payload()
    required_keys = {
        "participant_id",
        "field_type",
        "page_number",
        "x_pt",
        "y_pt",
        "width_pt",
        "height_pt",
    }
    if not required_keys.issubset(data.keys()):
        abort(
            400,
            description="participant_id, field_type, page_number, x_pt, y_pt, width_pt, height_pt required",
        )
    participant = db.session.get(EnvelopeParticipant, data["participant_id"])
    if participant is None or participant.envelope_id != envelope.id:
        abort(404, description="participant_not_found")
    try:
        row = fields_service.create_field(
            envelope,
            participant,
            field_type=str(data["field_type"]),
            page_number=int(data["page_number"]),
            rect=Rect(
                x_pt=float(data["x_pt"]),
                y_pt=float(data["y_pt"]),
                width_pt=float(data["width_pt"]),
                height_pt=float(data["height_pt"]),
            ),
            label=data.get("label"),
            required=bool(data.get("required", True)),
            created_by_id=user.id,
        )
    except fields_service.FieldError as exc:
        db.session.rollback()
        abort(400, description=str(exc))
    db.session.commit()
    return jsonify(_field_dict(row)), 201


@envelope_api.route(
    "/<int:envelope_id>/fields/<int:field_id>", methods=["DELETE"]
)
@jwt_required()
def delete_envelope_field(envelope_id, field_id):
    user = _actor()
    envelope = _owned(envelope_id, user, lock=True)
    try:
        fields_service.delete_field(envelope, field_id)
    except fields_service.FieldError as exc:
        db.session.rollback()
        abort(404, description=str(exc))
    db.session.commit()
    return jsonify(message="field_deleted"), 200


# ============================================================ Q1 labels


def _normalise_label(value):
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    if not value or len(value) > 60:
        return None
    for ch in value:
        if not (ch.isalnum() or ch in ("-", "_", ":")):
            return None
    return value


@envelope_api.route("/<int:envelope_id>/labels", methods=["POST"])
@jwt_required()
def add_envelope_label(envelope_id):
    """Attach a tenant-scoped label to an envelope."""
    user = _actor()
    envelope = _owned(envelope_id, user)
    data = _payload()
    label = _normalise_label(data.get("label"))
    if label is None:
        abort(400, description="label_invalid")
    existing = EnvelopeLabel.query.filter_by(
        envelope_id=envelope.id, label=label
    ).first()
    if existing is not None:
        return jsonify(label=label, created=False), 200
    row = EnvelopeLabel(
        envelope_id=envelope.id,
        organization_id=envelope.organization_id,
        label=label,
        created_by_id=user.id,
    )
    db.session.add(row)
    db.session.commit()
    return jsonify(label=label, created=True), 201


@envelope_api.route(
    "/<int:envelope_id>/labels/<path:label>", methods=["DELETE"]
)
@jwt_required()
def remove_envelope_label(envelope_id, label):
    user = _actor()
    envelope = _owned(envelope_id, user)
    normalised = _normalise_label(label)
    if normalised is None:
        abort(400, description="label_invalid")
    row = EnvelopeLabel.query.filter_by(
        envelope_id=envelope.id, label=normalised
    ).first()
    if row is None:
        abort(404)
    db.session.delete(row)
    db.session.commit()
    return jsonify(message="label_removed"), 200


@envelope_api.route("/<int:envelope_id>/labels", methods=["GET"])
@jwt_required()
def list_envelope_labels(envelope_id):
    user = _actor()
    envelope = _owned(envelope_id, user)
    labels = sorted(
        row.label
        for row in EnvelopeLabel.query.filter_by(envelope_id=envelope.id).all()
    )
    return jsonify(envelope_id=envelope.id, labels=labels)


# ============================================================ R1 cadence


@envelope_api.route("/<int:envelope_id>/reminders", methods=["PATCH"])
@jwt_required()
def update_reminder_cadence(envelope_id):
    """Set per-envelope reminder cadence overrides.

    ``cooloff_hours`` (1..720) controls the minimum gap between
    two reminders; ``max_count`` (1..50) caps the total number of
    reminders per invitation. ``null`` clears the override and
    reverts to the scanner's global default.
    """
    user = _actor()
    envelope = _owned(envelope_id, user, lock=True)
    data = _payload()
    allowed = {"cooloff_hours", "max_count"}
    extra = set(data) - allowed
    if extra:
        abort(400, description="unknown_fields")
    if "cooloff_hours" in data:
        cooloff = data["cooloff_hours"]
        if cooloff is not None and (
            type(cooloff) is not int or cooloff < 1 or cooloff > 720
        ):
            abort(400, description="cooloff_hours_out_of_range")
        envelope.reminder_cooloff_hours = cooloff
    if "max_count" in data:
        max_count = data["max_count"]
        if max_count is not None and (
            type(max_count) is not int or max_count < 1 or max_count > 50
        ):
            abort(400, description="max_count_out_of_range")
        envelope.reminder_max_count = max_count
    db.session.commit()
    return (
        jsonify(
            envelope_id=envelope.id,
            cooloff_hours=envelope.reminder_cooloff_hours,
            max_count=envelope.reminder_max_count,
        ),
        200,
    )


# ============================================================ R2 archival


_ARCHIVABLE_STATES = {"withdrawn", "cancelled", "superseded"}


@envelope_api.route("/<int:envelope_id>/archive", methods=["POST"])
@jwt_required()
def archive_envelope(envelope_id):
    """Soft-archive a terminal envelope.

    Archived envelopes are hidden from the default list but remain
    fully readable and auditable. Only terminal states
    (``withdrawn``, ``cancelled``, ``superseded``, ``completed``)
    can be archived.
    """
    user = _actor()
    envelope = _owned(envelope_id, user, lock=True)
    if envelope.state not in _ARCHIVABLE_STATES:
        abort(409, description="archive_requires_terminal_state")
    if envelope.archived_at is not None:
        return jsonify(_details(envelope)), 200
    envelope.archived_at = datetime.utcnow()
    envelope.archived_by_id = user.id
    db.session.commit()
    return jsonify(_details(envelope)), 200


@envelope_api.route("/<int:envelope_id>/unarchive", methods=["POST"])
@jwt_required()
def unarchive_envelope(envelope_id):
    user = _actor()
    envelope = _owned(envelope_id, user, lock=True)
    if envelope.archived_at is None:
        return jsonify(_details(envelope)), 200
    envelope.archived_at = None
    envelope.archived_by_id = None
    db.session.commit()
    return jsonify(_details(envelope)), 200


# ============================================================ V1 attachments


@envelope_api.route("/<int:envelope_id>/attachments", methods=["GET"])
@jwt_required()
def list_envelope_attachments(envelope_id):
    """List signer attachments bound to decisions on this envelope."""
    from app.models.signer_attachment import SignerAttachment
    from app.models.signer_decision import SignerDecision

    user = _actor()
    envelope = _owned(envelope_id, user)
    rows = (
        SignerAttachment.query.join(
            SignerDecision,
            SignerAttachment.decision_id == SignerDecision.id,
        )
        .filter(SignerAttachment.envelope_id == envelope.id)
        .order_by(SignerAttachment.id.asc())
        .all()
    )
    return jsonify(
        envelope_id=envelope.id,
        attachments=[
            {
                "id": row.id,
                "decision_id": row.decision_id,
                "participant_id": row.participant_id,
                "user_id": row.user_id,
                "file_name": row.file_name,
                "mime_type": row.mime_type,
                "file_size": row.file_size,
                "sha256": row.sha256,
                "scanner": row.scanner,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    )


@envelope_api.route(
    "/<int:envelope_id>/attachments/<int:attachment_id>/download",
    methods=["GET"],
)
@jwt_required()
def download_envelope_attachment(envelope_id, attachment_id):
    """Stream a bound attachment back to the envelope owner."""
    from app.models.signer_attachment import SignerAttachment
    from app.services.documents.private_object_store import active_store
    from flask import Response

    user = _actor()
    envelope = _owned(envelope_id, user)
    row = SignerAttachment.query.filter_by(
        id=attachment_id,
        envelope_id=envelope.id,
        organization_id=user.organization_id,
    ).first()
    if row is None:
        abort(404)
    if row.decision_id is None:
        # Staged rows are signer-scoped — the operator sees them
        # only after the decision has been recorded.
        abort(404)
    payload = active_store(current_app.config).read(
        row.object_key, config=current_app.config
    )
    headers = {
        "Content-Type": row.mime_type,
        "Content-Disposition": (
            f"attachment; filename=\"{row.file_name}\""
        ),
        "Cache-Control": "no-store",
        "X-TrustSeal-Attachment-SHA256": row.sha256,
    }
    return Response(payload, headers=headers)


# ============================================================ X2 bulk label


@envelope_api.route("/bulk/label", methods=["POST"])
@jwt_required()
def bulk_label_envelopes():
    """Attach a single label to many envelopes atomically.

    Payload: ``{"envelope_ids": [int, ...], "label": "<str>"}``.
    Idempotent per row — a row that already carries the label is
    reported with ``status="succeeded"`` and ``already_tagged=True``.
    Rows the caller does not own return ``envelope_not_found``.
    """
    user = _actor()
    data = _payload()
    ids = data.get("envelope_ids")
    label_raw = data.get("label")
    if not isinstance(ids, list) or not ids:
        abort(400, description="envelope_ids_required")
    if len(ids) > 100:
        abort(413, description="bulk_label_limit_100")
    label = _normalise_label(label_raw)
    if label is None:
        abort(400, description="label_invalid")

    seen: set[int] = set()
    results: list[dict] = []
    added = 0
    for env_id in ids:
        entry = {"envelope_id": env_id}
        if type(env_id) is not int:
            entry["status"] = "failed"
            entry["error_code"] = "envelope_id_invalid"
            results.append(entry)
            continue
        if env_id in seen:
            entry["status"] = "failed"
            entry["error_code"] = "duplicate_id"
            results.append(entry)
            continue
        seen.add(env_id)
        envelope = SigningEnvelope.query.filter_by(
            id=env_id,
            organization_id=user.organization_id,
            created_by_id=user.id,
        ).first()
        if envelope is None:
            entry["status"] = "failed"
            entry["error_code"] = "envelope_not_found"
            results.append(entry)
            continue
        existing = EnvelopeLabel.query.filter_by(
            envelope_id=envelope.id, label=label
        ).first()
        if existing is not None:
            entry["status"] = "succeeded"
            entry["already_tagged"] = True
            results.append(entry)
            continue
        db.session.add(
            EnvelopeLabel(
                envelope_id=envelope.id,
                organization_id=envelope.organization_id,
                label=label,
                created_by_id=user.id,
            )
        )
        added += 1
        entry["status"] = "succeeded"
        entry["already_tagged"] = False
        results.append(entry)

    succeeded = sum(1 for r in results if r["status"] == "succeeded")
    failed = len(results) - succeeded
    if succeeded == 0:
        db.session.rollback()
        return (
            jsonify(
                label=label,
                succeeded=0,
                failed=failed,
                results=results,
            ),
            400,
        )
    db.session.commit()
    http_status = 207 if failed else 200
    return (
        jsonify(
            label=label,
            succeeded=succeeded,
            failed=failed,
            added=added,
            results=results,
        ),
        http_status,
    )
