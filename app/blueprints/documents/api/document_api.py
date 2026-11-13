"""Tenant-aware document metadata endpoints.

The legacy document API contained placeholder CRUD methods. These endpoints
intentionally manage draft metadata only; evidence and signed records must be
handled by immutable document workflows, not generic CRUD.
"""
from datetime import datetime

from flask import Blueprint, abort, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import or_

from app.extensions import db
from app.models.documents.document import Document
from app.models.documents.document_share import DocumentShare
from app.models.user import User

document_api = Blueprint("document_api", __name__, url_prefix="/api/documents")
EDITABLE = {"title", "description", "content", "tags", "document_type_id"}
IMMUTABLE = {"signed", "final", "completed", "archived", "disposed"}


def actor():
    try:
        user = db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        user = None
    if user is None or not user.is_active:
        abort(401)
    return user


def _access_query(user, write=False):
    """Never grant access to every document in an organisation by default."""
    owned = Document.created_by == user.id
    if write:
        return owned
    shared = db.session.query(DocumentShare.document_id).filter(
        DocumentShare.shared_with_user_id == user.id,
        DocumentShare.can_view.is_(True),
        or_(DocumentShare.expires_at.is_(None), DocumentShare.expires_at > datetime.utcnow()),
    )
    return or_(owned, Document.id.in_(shared))


def get_authorized_document_or_abort(document_id, check_ownership_only=False):
    user = actor()
    doc = Document.query.filter(
        Document.id == document_id,
        Document.deleted_at.is_(None),
        _access_query(user, write=check_ownership_only),
    ).first()
    if doc is None:
        abort(404)
    return doc


def _serialize(doc, content=False):
    """Avoid exposing server paths, shares, tokens or nested user profiles."""
    data = {
        "id": doc.id, "title": doc.title, "description": doc.description,
        "status": doc.status, "document_type_id": doc.document_type_id,
        "tags": doc.tags, "version": doc.version,
        "organization_id": doc.organization_id, "created_by_id": doc.created_by,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    }
    if content:
        data["content"] = doc.content
    return data


def _payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="JSON object required")
    return data


def _validate(data, creating=False):
    if creating or "title" in data:
        if not isinstance(data.get("title"), str) or not 1 <= len(data["title"].strip()) <= 200:
            abort(400, description="Title must be 1-200 characters")
    for key in ("description", "content", "tags"):
        if key in data and data[key] is not None and not isinstance(data[key], str):
            abort(400, description=f"{key} must be text")
    if "document_type_id" in data and data["document_type_id"] is not None:
        if type(data["document_type_id"]) is not int or data["document_type_id"] <= 0:
            abort(400, description="Invalid document type")


@document_api.route("/mine", methods=["GET"])
@jwt_required()
def list_user_documents():
    user = actor()
    docs = Document.query.filter(
        Document.created_by == user.id, Document.deleted_at.is_(None)
    ).order_by(Document.updated_at.desc()).limit(100).all()
    return jsonify([_serialize(doc) for doc in docs])


@document_api.route("/", methods=["GET"])
@jwt_required()
def list_documents():
    user = actor()
    docs = Document.query.filter(
        Document.deleted_at.is_(None), _access_query(user)
    ).order_by(Document.updated_at.desc()).limit(100).all()
    return jsonify([_serialize(doc) for doc in docs])


@document_api.route("/<int:document_id>/", methods=["GET"])
@jwt_required()
def get_document(document_id):
    return jsonify(_serialize(get_authorized_document_or_abort(document_id), content=True))


@document_api.route("/", methods=["POST"])
@jwt_required()
def create_document():
    user = actor()
    data = _payload()
    _validate(data, creating=True)
    doc = Document(
        created_by=user.id, organization_id=user.organization_id,
        status="draft", version=1, title=data["title"].strip(),
    )
    for key in EDITABLE - {"title"}:
        if key in data:
            setattr(doc, key, data[key])
    db.session.add(doc)
    db.session.commit()
    return jsonify(_serialize(doc)), 201


@document_api.route("/<int:document_id>/", methods=["PUT"])
@jwt_required()
def update_document(document_id):
    doc = get_authorized_document_or_abort(document_id, check_ownership_only=True)
    if (doc.status or "").lower() != "draft":
        abort(409, description="Only drafts are editable")
    data = _payload()
    _validate(data)
    for key in EDITABLE:
        if key in data:
            setattr(doc, key, data[key].strip() if key == "title" else data[key])
    doc.last_modified_by_id = actor().id
    doc.version = (doc.version or 0) + 1
    db.session.commit()
    return jsonify(_serialize(doc))


@document_api.route("/<int:document_id>/", methods=["DELETE"])
@jwt_required()
def delete_document(document_id):
    doc = get_authorized_document_or_abort(document_id, check_ownership_only=True)
    if (doc.status or "").lower() != "draft":
        abort(409, description="Non-draft documents cannot be deleted")
    doc.deleted_at = datetime.utcnow()
    db.session.commit()
    return "", 204


# === Immutable draft-text snapshots (not completed legal evidence) ===
@document_api.route("/<int:document_id>/snapshots", methods=["POST"])
@jwt_required()
def create_draft_snapshot(document_id):
    from sqlalchemy.exc import IntegrityError
    from app.models.documents.document_snapshot import DocumentSnapshot
    from app.models.documents.document_activity import DocumentActivity
    from app.services.documents.snapshots import snapshot_digest

    user = actor()
    # Serialize concurrent writers before checking the revision.
    doc = Document.query.filter_by(
        id=document_id, created_by=user.id, deleted_at=None
    ).with_for_update().first()
    if doc is None:
        abort(404)
    if (doc.status or "").lower() != "draft":
        abort(409, description="Only draft text can be snapshotted")
    if not isinstance(doc.content, str):
        abort(409, description="Document has no text content")
    if len(doc.content.encode("utf-8")) > 1024 * 1024:
        abort(413, description="Draft text exceeds snapshot limit")
    revision = doc.version or 1
    digest = snapshot_digest(doc.id, revision, doc.content)
    prior = DocumentSnapshot.query.filter_by(
        document_id=doc.id, revision=revision
    ).first()
    if prior is not None:
        if prior.content_sha256 != digest:
            abort(409, description="Revision content conflict")
        return jsonify(_snapshot_meta(prior)), 200
    record = DocumentSnapshot(
        document_id=doc.id, revision=revision, content_sha256=digest,
        canonical_content=doc.content, created_by_id=user.id,
    )
    db.session.add(record)
    db.session.add(DocumentActivity(
        document_id=doc.id, user_id=user.id,
        activity_type="draft_snapshot_created",
        details="Draft revision %s, SHA-256 %s" % (revision, digest),
    ))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        abort(409, description="Snapshot revision conflict")
    return jsonify(_snapshot_meta(record)), 201


def _snapshot_meta(snapshot):
    return {
        "id": snapshot.id, "document_id": snapshot.document_id,
        "revision": snapshot.revision, "sha256": snapshot.content_sha256,
        "created_by_id": snapshot.created_by_id,
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        "assurance": "draft_text_integrity_only",
    }


@document_api.route("/<int:document_id>/snapshots", methods=["GET"])
@jwt_required()
def list_draft_snapshots(document_id):
    from app.models.documents.document_snapshot import DocumentSnapshot
    get_authorized_document_or_abort(document_id)
    records = DocumentSnapshot.query.filter_by(document_id=document_id).order_by(
        DocumentSnapshot.revision.desc()
    ).limit(100).all()
    return jsonify([_snapshot_meta(record) for record in records])


@document_api.route("/<int:document_id>/snapshots/<int:snapshot_id>", methods=["GET"])
@jwt_required()
def get_draft_snapshot(document_id, snapshot_id):
    from app.models.documents.document_snapshot import DocumentSnapshot
    get_authorized_document_or_abort(document_id)
    record = DocumentSnapshot.query.filter_by(
        id=snapshot_id, document_id=document_id
    ).first_or_404()
    result = _snapshot_meta(record)
    result["content"] = record.canonical_content
    return jsonify(result)


@document_api.route("/<int:document_id>/snapshots/<int:snapshot_id>/integrity", methods=["GET"])
@jwt_required()
def check_draft_snapshot_integrity(document_id, snapshot_id):
    """Recompute stored draft-text digest; does not attest external storage."""
    import hmac
    from app.models.documents.document_snapshot import DocumentSnapshot
    from app.services.documents.snapshots import snapshot_digest

    get_authorized_document_or_abort(document_id)
    record = DocumentSnapshot.query.filter_by(
        id=snapshot_id, document_id=document_id
    ).first_or_404()
    actual = snapshot_digest(
        record.document_id, record.revision, record.canonical_content
    )
    verified = hmac.compare_digest(actual, record.content_sha256)
    return jsonify({
        **_snapshot_meta(record),
        "integrity": "MATCH" if verified else "MISMATCH",
        "verified": verified,
        "assurance": "stored_draft_text_digest_only",
    })
