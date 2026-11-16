"""Document label CRUD (Phase Y1).

Mirror of the envelope label surface in :mod:`envelope_api`, scoped
to a document. Documents the operator owns within their tenant can
carry up to any number of normalised labels; the label strings are
tenant-local (another tenant's ``finance`` label is a separate row).
"""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.documents.document import Document
from app.models.documents.document_label import DocumentLabel
from app.services.token_security import active_token_user


document_label_api = Blueprint(
    "document_label_api",
    __name__,
    url_prefix="/api/documents",
)


def _actor():
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    if user.organization_id is None:
        abort(403)
    return user


def _owned(document_id: int, user):
    doc = Document.query.filter_by(
        id=document_id,
        organization_id=user.organization_id,
        created_by=user.id,
        deleted_at=None,
    ).first()
    if doc is None:
        abort(404)
    return doc


def _payload():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        abort(400, description="JSON object required")
    return value


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


@document_label_api.route("/<int:document_id>/labels", methods=["POST"])
@jwt_required()
def add_document_label(document_id: int):
    user = _actor()
    doc = _owned(document_id, user)
    data = _payload()
    label = _normalise_label(data.get("label"))
    if label is None:
        abort(400, description="label_invalid")
    existing = DocumentLabel.query.filter_by(
        document_id=doc.id, label=label
    ).first()
    if existing is not None:
        return jsonify(label=label, created=False), 200
    row = DocumentLabel(
        document_id=doc.id,
        organization_id=doc.organization_id,
        label=label,
        created_by_id=user.id,
    )
    db.session.add(row)
    db.session.commit()
    return jsonify(label=label, created=True), 201


@document_label_api.route(
    "/<int:document_id>/labels/<path:label>", methods=["DELETE"]
)
@jwt_required()
def remove_document_label(document_id: int, label: str):
    user = _actor()
    doc = _owned(document_id, user)
    normalised = _normalise_label(label)
    if normalised is None:
        abort(400, description="label_invalid")
    row = DocumentLabel.query.filter_by(
        document_id=doc.id, label=normalised
    ).first()
    if row is None:
        abort(404)
    db.session.delete(row)
    db.session.commit()
    return jsonify(message="label_removed"), 200


@document_label_api.route("/<int:document_id>/labels", methods=["GET"])
@jwt_required()
def list_document_labels(document_id: int):
    user = _actor()
    doc = _owned(document_id, user)
    labels = sorted(
        row.label
        for row in DocumentLabel.query.filter_by(document_id=doc.id).all()
    )
    return jsonify(document_id=doc.id, labels=labels)


@document_label_api.route("/by-label/<path:label>", methods=["GET"])
@jwt_required()
def list_documents_by_label(label: str):
    """List documents carrying a specific label."""
    user = _actor()
    normalised = _normalise_label(label)
    if normalised is None:
        abort(400, description="label_invalid")
    rows = (
        db.session.query(Document)
        .join(DocumentLabel, DocumentLabel.document_id == Document.id)
        .filter(
            Document.organization_id == user.organization_id,
            Document.created_by == user.id,
            Document.deleted_at.is_(None),
            DocumentLabel.label == normalised,
        )
        .order_by(Document.id.desc())
        .limit(200)
        .all()
    )
    return jsonify(
        label=normalised,
        documents=[
            {
                "id": doc.id,
                "title": doc.title,
                "status": doc.status,
                "created_at": doc.created_at.isoformat()
                if doc.created_at
                else None,
            }
            for doc in rows
        ],
    )
