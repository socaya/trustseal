"""Authenticated, owner-governed document sharing.

Only existing active users in the document's organisation may receive a
direct share. External invitation and delegated signing are separate
workflows, not implicit permissions granted through generic CRUD.
"""
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, abort, jsonify, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.user import User
from app.models.documents.document import Document
from app.models.documents.document_share import DocumentShare
from app.services.token_security import active_token_user

document_share_api = Blueprint("document_share_api", __name__, url_prefix="/api/document-shares")


def _actor():
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    return user


def _payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="JSON object required")
    return data


def _document_for_owner(document_id, user):
    doc = db.session.get(Document, document_id)
    if doc is None or doc.deleted_at is not None or doc.created_by != user.id:
        abort(404)
    return doc


def _owned_share(item_id, user):
    share = db.session.get(DocumentShare, item_id)
    if share is None:
        abort(404)
    _document_for_owner(share.document_id, user)
    return share


def _serialize(share):
    return {
        "id": share.id, "document_id": share.document_id,
        "shared_with_user_id": share.shared_with_user_id,
        "can_view": bool(share.can_view), "can_download": bool(share.can_download),
        "expires_at": share.expires_at.isoformat() if share.expires_at else None,
        "created_at": share.created_at.isoformat() if share.created_at else None,
    }


@document_share_api.route("/", methods=["GET"])
@jwt_required()
def list_document_shares():
    user = _actor()
    items = db.session.query(DocumentShare).join(
        Document, DocumentShare.document_id == Document.id
    ).filter(
        Document.created_by == user.id, Document.deleted_at.is_(None)
    ).limit(100).all()
    return jsonify([_serialize(item) for item in items])


@document_share_api.route("/<int:item_id>", methods=["GET"])
@jwt_required()
def get_document_share(item_id):
    return jsonify(_serialize(_owned_share(item_id, _actor())))


@document_share_api.route("/", methods=["POST"])
@jwt_required()
def create_document_share():
    user = _actor()
    data = _payload()
    document_id = data.get("document_id")
    recipient_id = data.get("shared_with_user_id")
    if type(document_id) is not int or type(recipient_id) is not int:
        abort(400, description="Document and recipient IDs are required")
    doc = _document_for_owner(document_id, user)
    recipient = db.session.get(User, recipient_id)
    if recipient is None or not recipient.is_active or recipient.id == user.id:
        abort(400, description="An active recipient other than the owner is required")
    if doc.organization_id is None or recipient.organization_id != doc.organization_id:
        abort(403, description="Cross-organisation sharing requires a verified invitation")
    can_download = data.get("can_download", False)
    if type(can_download) is not bool:
        abort(400, description="can_download must be a boolean")
    if DocumentShare.query.filter_by(
        document_id=doc.id, shared_with_user_id=recipient.id
    ).first():
        abort(409, description="A share for this recipient already exists")
    share = DocumentShare(
        document_id=doc.id, shared_with_user_id=recipient.id,
        created_by_id=user.id, token=secrets.token_urlsafe(32),
        expires_at=datetime.utcnow() + timedelta(days=7),
        can_view=True, can_download=can_download,
        can_edit=False, can_sign=False, can_stamp=False, can_share=False,
    )
    db.session.add(share)
    db.session.commit()
    return jsonify(_serialize(share)), 201


@document_share_api.route("/<int:item_id>", methods=["PUT"])
@jwt_required()
def update_document_share(item_id):
    user = _actor()
    share = _owned_share(item_id, user)
    data = _payload()
    if set(data) != {"can_download"} or type(data["can_download"]) is not bool:
        abort(400, description="Only can_download may be updated")
    share.can_download = data["can_download"]
    db.session.commit()
    return jsonify(_serialize(share))


@document_share_api.route("/<int:item_id>", methods=["DELETE"])
@jwt_required()
def delete_document_share(item_id):
    share = _owned_share(item_id, _actor())
    db.session.delete(share)
    db.session.commit()
    return "", 204
