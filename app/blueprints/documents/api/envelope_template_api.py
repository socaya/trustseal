"""Envelope template CRUD + instantiate (Phase S1).

Operators often re-send the same envelope shape — routing,
cadence, participants — against a fresh document. Templates
capture that reusable shape and the ``/instantiate`` endpoint
mints a draft envelope with the template's settings and
participants pre-populated.

All endpoints are tenant-scoped via ``active_token_user()`` and
match the private envelope API's error contract.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, abort, current_app, jsonify, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.documents.document import Document
from app.models.documents.document_blob import DocumentBlob
from app.models.envelope_template import (
    EnvelopeTemplate,
    EnvelopeTemplateParticipant,
)
from app.models.signing_envelope import (
    EnvelopeParticipant,
    SigningEnvelope,
)
from app.models.user import User
from app.services.documents.private_storage import (
    IngestionError,
    check_object_digest,
)
from app.services.event_delivery import enqueue
from app.services.token_security import active_token_user

envelope_template_api = Blueprint(
    "envelope_template_api",
    __name__,
    url_prefix="/api/envelope-templates",
)


# ============================================================ helpers


def _actor():
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    if user.organization_id is None:
        abort(403)
    return user


def _payload():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        abort(400, description="JSON object required")
    return value


def _own_template(template_id: int, user, lock: bool = False):
    query = EnvelopeTemplate.query.filter_by(
        id=template_id, organization_id=user.organization_id
    )
    item = (query.with_for_update() if lock else query).first()
    if item is None:
        abort(404)
    return item


def _validate_routing(data: dict) -> tuple[str, int | None]:
    mode = data.get("routing_mode", "sequential")
    if mode not in ("sequential", "parallel", "quorum"):
        abort(400, description="routing_mode must be sequential|parallel|quorum")
    quorum = data.get("quorum_required")
    if mode == "quorum":
        if not isinstance(quorum, int) or quorum < 1:
            abort(400, description="quorum_required must be positive integer")
    else:
        if quorum is not None:
            abort(400, description="quorum_required only valid for quorum mode")
    return mode, quorum


def _validate_cadence(data: dict) -> tuple[int | None, int | None]:
    cooloff = data.get("reminder_cooloff_hours")
    if cooloff is not None and (
        type(cooloff) is not int or cooloff < 1 or cooloff > 720
    ):
        abort(400, description="reminder_cooloff_hours_out_of_range")
    max_count = data.get("reminder_max_count")
    if max_count is not None and (
        type(max_count) is not int or max_count < 1 or max_count > 50
    ):
        abort(400, description="reminder_max_count_out_of_range")
    return cooloff, max_count


def _validate_expires_in(data: dict) -> int | None:
    value = data.get("expires_in_hours")
    if value is not None and (
        type(value) is not int or value < 1 or value > 8760
    ):
        abort(400, description="expires_in_hours_out_of_range")
    return value


def _participant_dict(row: EnvelopeTemplateParticipant) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "signing_order": row.signing_order,
        "role": row.role,
    }


def _dict(template: EnvelopeTemplate) -> dict:
    rows = (
        EnvelopeTemplateParticipant.query.filter_by(
            template_id=template.id
        )
        .order_by(EnvelopeTemplateParticipant.signing_order)
        .all()
    )
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "routing_mode": template.routing_mode,
        "quorum_required": template.quorum_required,
        "reminder_cooloff_hours": template.reminder_cooloff_hours,
        "reminder_max_count": template.reminder_max_count,
        "expires_in_hours": template.expires_in_hours,
        "created_by_id": template.created_by_id,
        "created_at": template.created_at.isoformat(),
        "updated_at": template.updated_at.isoformat(),
        "participants": [_participant_dict(r) for r in rows],
    }


# ============================================================ CRUD


@envelope_template_api.route("", methods=["POST"])
@jwt_required()
def create_template():
    user = _actor()
    data = _payload()
    allowed = {
        "name",
        "description",
        "routing_mode",
        "quorum_required",
        "reminder_cooloff_hours",
        "reminder_max_count",
        "expires_in_hours",
    }
    extra = set(data) - allowed
    if extra:
        abort(400, description="unknown_fields")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        abort(400, description="name_required")
    description = data.get("description")
    if description is not None and (
        not isinstance(description, str) or len(description) > 400
    ):
        abort(400, description="description_invalid")
    mode, quorum = _validate_routing(data)
    cooloff, max_count = _validate_cadence(data)
    expires_in = _validate_expires_in(data)
    row = EnvelopeTemplate(
        organization_id=user.organization_id,
        name=name.strip(),
        description=description,
        routing_mode=mode,
        quorum_required=quorum,
        reminder_cooloff_hours=cooloff,
        reminder_max_count=max_count,
        expires_in_hours=expires_in,
        created_by_id=user.id,
    )
    db.session.add(row)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        abort(409, description="template_name_already_exists")
    return jsonify(_dict(row)), 201


@envelope_template_api.route("", methods=["GET"])
@jwt_required()
def list_templates():
    user = _actor()
    rows = (
        EnvelopeTemplate.query.filter_by(organization_id=user.organization_id)
        .order_by(EnvelopeTemplate.id.desc())
        .limit(200)
        .all()
    )
    return jsonify([_dict(r) for r in rows])


@envelope_template_api.route("/<int:template_id>", methods=["GET"])
@jwt_required()
def get_template(template_id: int):
    user = _actor()
    return jsonify(_dict(_own_template(template_id, user)))


@envelope_template_api.route("/<int:template_id>", methods=["PATCH"])
@jwt_required()
def update_template(template_id: int):
    user = _actor()
    template = _own_template(template_id, user, lock=True)
    data = _payload()
    allowed = {
        "name",
        "description",
        "routing_mode",
        "quorum_required",
        "reminder_cooloff_hours",
        "reminder_max_count",
        "expires_in_hours",
    }
    extra = set(data) - allowed
    if extra:
        abort(400, description="unknown_fields")
    if "name" in data:
        name = data["name"]
        if not isinstance(name, str) or not name.strip():
            abort(400, description="name_required")
        template.name = name.strip()
    if "description" in data:
        description = data["description"]
        if description is not None and (
            not isinstance(description, str) or len(description) > 400
        ):
            abort(400, description="description_invalid")
        template.description = description
    if "routing_mode" in data or "quorum_required" in data:
        # Evaluate as a pair since quorum_required depends on routing_mode.
        merged = {
            "routing_mode": data.get("routing_mode", template.routing_mode),
            "quorum_required": data.get(
                "quorum_required", template.quorum_required
            ),
        }
        mode, quorum = _validate_routing(merged)
        template.routing_mode = mode
        template.quorum_required = quorum
    if "reminder_cooloff_hours" in data:
        value = data["reminder_cooloff_hours"]
        if value is not None and (
            type(value) is not int or value < 1 or value > 720
        ):
            abort(400, description="reminder_cooloff_hours_out_of_range")
        template.reminder_cooloff_hours = value
    if "reminder_max_count" in data:
        value = data["reminder_max_count"]
        if value is not None and (
            type(value) is not int or value < 1 or value > 50
        ):
            abort(400, description="reminder_max_count_out_of_range")
        template.reminder_max_count = value
    if "expires_in_hours" in data:
        value = data["expires_in_hours"]
        if value is not None and (
            type(value) is not int or value < 1 or value > 8760
        ):
            abort(400, description="expires_in_hours_out_of_range")
        template.expires_in_hours = value
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        abort(409, description="template_name_already_exists")
    return jsonify(_dict(template))


@envelope_template_api.route("/<int:template_id>", methods=["DELETE"])
@jwt_required()
def delete_template(template_id: int):
    user = _actor()
    template = _own_template(template_id, user, lock=True)
    db.session.delete(template)
    db.session.commit()
    return jsonify(message="template_deleted"), 200


# ============================================================ participants


@envelope_template_api.route(
    "/<int:template_id>/participants", methods=["POST"]
)
@jwt_required()
def add_template_participant(template_id: int):
    user = _actor()
    template = _own_template(template_id, user, lock=True)
    data = _payload()
    if set(data) - {"user_id", "signing_order", "role"}:
        abort(400, description="unknown_fields")
    recipient_id = data.get("user_id")
    order = data.get("signing_order")
    role = data.get("role", "signer")
    if type(recipient_id) is not int or type(order) is not int or order < 1:
        abort(400, description="fields_invalid")
    if role not in ("signer", "witness"):
        abort(400, description="role_invalid")
    recipient = db.session.get(User, recipient_id)
    if (
        recipient is None
        or not recipient.is_active
        or recipient.organization_id != user.organization_id
    ):
        abort(404, description="recipient_not_found")
    dup_user = (
        EnvelopeTemplateParticipant.query.filter_by(
            template_id=template.id, user_id=recipient_id
        ).first()
    )
    if dup_user is not None:
        abort(409, description="duplicate_user")
    dup_order = (
        EnvelopeTemplateParticipant.query.filter_by(
            template_id=template.id, signing_order=order
        ).first()
    )
    if dup_order is not None:
        abort(409, description="duplicate_signing_order")
    row = EnvelopeTemplateParticipant(
        template_id=template.id,
        user_id=recipient_id,
        signing_order=order,
        role=role,
    )
    db.session.add(row)
    db.session.commit()
    return jsonify(_participant_dict(row)), 201


@envelope_template_api.route(
    "/<int:template_id>/participants/<int:participant_id>",
    methods=["DELETE"],
)
@jwt_required()
def remove_template_participant(template_id: int, participant_id: int):
    user = _actor()
    template = _own_template(template_id, user, lock=True)
    row = EnvelopeTemplateParticipant.query.filter_by(
        id=participant_id, template_id=template.id
    ).first()
    if row is None:
        abort(404)
    db.session.delete(row)
    db.session.commit()
    return jsonify(message="participant_removed"), 200


# ============================================================ instantiate


@envelope_template_api.route(
    "/<int:template_id>/instantiate", methods=["POST"]
)
@jwt_required()
def instantiate_template(template_id: int):
    """Mint a draft SigningEnvelope using the template's settings."""
    user = _actor()
    template = _own_template(template_id, user)
    data = _payload()
    allowed = {"document_id", "document_blob_id"}
    if set(data) - allowed:
        abort(400, description="unknown_fields")
    document_id = data.get("document_id")
    blob_id = data.get("document_blob_id")
    if type(document_id) is not int or type(blob_id) is not int:
        abort(400, description="document_id_and_blob_id_required")
    doc = Document.query.filter_by(
        id=document_id,
        created_by=user.id,
        organization_id=user.organization_id,
        deleted_at=None,
    ).first()
    if doc is None:
        abort(404, description="document_not_found")
    if (doc.status or "").lower() not in {"draft", "pending"}:
        abort(409, description="document_not_eligible")
    blob = DocumentBlob.query.filter_by(id=blob_id, document_id=doc.id).first()
    if blob is None:
        abort(404, description="blob_not_found")
    try:
        check_object_digest(blob.object_key, blob.sha256, current_app.config)
    except IngestionError:
        abort(503, description="stored_document_integrity_unavailable")
    participants = (
        EnvelopeTemplateParticipant.query.filter_by(template_id=template.id)
        .order_by(EnvelopeTemplateParticipant.signing_order)
        .all()
    )
    expires_at = (
        datetime.utcnow() + timedelta(hours=template.expires_in_hours)
        if template.expires_in_hours is not None
        else None
    )
    envelope = SigningEnvelope(
        organization_id=user.organization_id,
        document_id=doc.id,
        document_blob_id=blob.id,
        document_sha256=blob.sha256,
        created_by_id=user.id,
        state="draft",
        routing_mode=template.routing_mode,
        quorum_required=template.quorum_required,
        reminder_cooloff_hours=template.reminder_cooloff_hours,
        reminder_max_count=template.reminder_max_count,
        expires_at=expires_at,
    )
    db.session.add(envelope)
    db.session.flush()
    # Re-verify recipients are still active tenant members. If any
    # member of the roster has been deactivated or moved tenants
    # since the template was authored, surface that as a 409 with
    # the stale user id so the operator can fix the template.
    stale = []
    for tp in participants:
        recipient = db.session.get(User, tp.user_id)
        if (
            recipient is None
            or not recipient.is_active
            or recipient.organization_id != user.organization_id
        ):
            stale.append(tp.user_id)
    if stale:
        db.session.rollback()
        return (
            jsonify(
                error="stale_template_participants",
                user_ids=stale,
            ),
            409,
        )
    for tp in participants:
        db.session.add(
            EnvelopeParticipant(
                envelope_id=envelope.id,
                user_id=tp.user_id,
                signing_order=tp.signing_order,
                role=tp.role,
            )
        )
    enqueue(
        event_type="envelope.draft.created",
        aggregate_type="envelope",
        aggregate_id=envelope.id,
        organization_id=user.organization_id,
        actor_id=user.id,
        action="envelope.draft.created",
        idempotency_key="envelope-created:%s" % envelope.id,
    )
    enqueue(
        event_type="envelope.template.instantiated",
        aggregate_type="envelope_template",
        aggregate_id=template.id,
        organization_id=user.organization_id,
        actor_id=user.id,
        action="envelope.template.instantiated",
        idempotency_key="envelope-template-instantiated:%s:%s"
        % (template.id, envelope.id),
    )
    db.session.commit()
    return (
        jsonify(
            template_id=template.id,
            envelope_id=envelope.id,
            participants_created=len(participants),
        ),
        201,
    )
