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
from app.models.signing_envelope import SigningEnvelope, EnvelopeParticipant
from app.services.token_security import active_token_user
from app.services.event_delivery import enqueue
from app.services.documents.private_storage import check_object_digest, IngestionError

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
    return {
        "id": item.id, "document_id": item.document_id,
        "document_blob_id": item.document_blob_id,
        "document_sha256": item.document_sha256,
        "state": item.state, "created_by_id": item.created_by_id,
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
    if set(data) != {"document_id", "document_blob_id"}:
        abort(400, description="document_id and document_blob_id required")
    document_id, blob_id = data["document_id"], data["document_blob_id"]
    if type(document_id) is not int or type(blob_id) is not int:
        abort(400)
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
    envelope = SigningEnvelope(
        document_id=doc.id, document_blob_id=blob.id,
        document_sha256=blob.sha256, organization_id=user.organization_id,
        created_by_id=user.id, state="draft",
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
    items = SigningEnvelope.query.filter_by(
        created_by_id=user.id, organization_id=user.organization_id
    ).order_by(SigningEnvelope.id.desc()).limit(100).all()
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


@envelope_api.route("/<int:envelope_id>/prepare", methods=["POST"])
@jwt_required()
def prepare_envelope(envelope_id):
    user = _actor()
    envelope = _owned(envelope_id, user, lock=True)
    if envelope.state != "draft":
        abort(409, description="Envelope is no longer editable")
    participants = EnvelopeParticipant.query.filter_by(
        envelope_id=envelope.id
    ).order_by(EnvelopeParticipant.signing_order).all()
    if not participants or [p.signing_order for p in participants] != list(range(1, len(participants) + 1)):
        abort(409, description="Continuous signing order from 1 required")
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
    db.session.commit()
    return jsonify(_details(envelope))


@envelope_api.route("/<int:envelope_id>/cancel", methods=["POST"])
@jwt_required()
def cancel_envelope(envelope_id):
    user = _actor()
    envelope = _owned(envelope_id, user, lock=True)
    if envelope.state == "cancelled":
        return jsonify(_details(envelope))
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
