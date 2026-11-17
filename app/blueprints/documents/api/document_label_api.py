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


@document_label_api.route("/<int:document_id>/activity", methods=["GET"])
@jwt_required()
def document_activity(document_id: int):
    """Return a chronological SecurityEvent slice for one document (Phase Z2).

    Query params: ``since`` / ``until`` ISO-8601 bounds, ``limit``
    1..500 (default 100). Results are ordered oldest-first.
    """
    from datetime import datetime
    from app.models.event_delivery import SecurityEvent

    user = _actor()
    doc = _owned(document_id, user)
    since_raw = request.args.get("since")
    until_raw = request.args.get("until")
    limit_raw = request.args.get("limit")
    since = None
    until = None
    if since_raw:
        try:
            since = datetime.fromisoformat(since_raw)
        except ValueError:
            abort(400, description="since_invalid_iso")
    if until_raw:
        try:
            until = datetime.fromisoformat(until_raw)
        except ValueError:
            abort(400, description="until_invalid_iso")
    try:
        limit = int(limit_raw) if limit_raw else 100
    except ValueError:
        abort(400, description="limit_invalid")
    if limit < 1 or limit > 500:
        abort(400, description="limit_out_of_range")
    query = SecurityEvent.query.filter(
        SecurityEvent.organization_id == user.organization_id,
        SecurityEvent.resource_type == "document",
        SecurityEvent.resource_id == doc.id,
    )
    if since is not None:
        query = query.filter(SecurityEvent.created_at >= since)
    if until is not None:
        query = query.filter(SecurityEvent.created_at <= until)
    rows = query.order_by(SecurityEvent.id.asc()).limit(limit).all()
    return jsonify(
        document_id=doc.id,
        events=[
            {
                "id": row.id,
                "actor_id": row.actor_id,
                "action": row.action,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "outcome": row.outcome,
                "correlation_id": row.correlation_id,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    )


@document_label_api.route("/labels", methods=["GET"])
@jwt_required()
def list_tenant_document_labels():
    """Return the unique document labels used in the caller's tenant (Phase AG2)."""
    from sqlalchemy import func

    user = _actor()
    rows = (
        db.session.query(DocumentLabel.label, func.count(DocumentLabel.id))
        .filter(DocumentLabel.organization_id == user.organization_id)
        .group_by(DocumentLabel.label)
        .order_by(DocumentLabel.label.asc())
        .all()
    )
    return jsonify(
        organization_id=user.organization_id,
        labels=[{"label": label, "count": int(count)} for label, count in rows],
    )


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


# ============================================================ AK bulk ops


@document_label_api.route("/bulk/label", methods=["POST"])
@jwt_required()
def bulk_tag_documents():
    """Attach a single label to up to 100 documents atomically.

    Payload: ``{"document_ids": [int, ...], "label": "<str>"}``.
    Rows already carrying the label report ``succeeded`` with
    ``already_tagged=True``. Rows the caller does not own return
    ``document_not_found``.
    """
    user = _actor()
    data = _payload()
    ids = data.get("document_ids")
    label_raw = data.get("label")
    if not isinstance(ids, list) or not ids:
        abort(400, description="document_ids_required")
    if len(ids) > 100:
        abort(413, description="bulk_label_limit_100")
    label = _normalise_label(label_raw)
    if label is None:
        abort(400, description="label_invalid")

    seen: set[int] = set()
    results: list[dict] = []
    added = 0
    for doc_id in ids:
        entry = {"document_id": doc_id}
        if type(doc_id) is not int:
            entry["status"] = "failed"
            entry["error_code"] = "document_id_invalid"
            results.append(entry)
            continue
        if doc_id in seen:
            entry["status"] = "failed"
            entry["error_code"] = "duplicate_id"
            results.append(entry)
            continue
        seen.add(doc_id)
        doc = Document.query.filter_by(
            id=doc_id,
            organization_id=user.organization_id,
            created_by=user.id,
            deleted_at=None,
        ).first()
        if doc is None:
            entry["status"] = "failed"
            entry["error_code"] = "document_not_found"
            results.append(entry)
            continue
        existing = DocumentLabel.query.filter_by(
            document_id=doc.id, label=label
        ).first()
        if existing is not None:
            entry["status"] = "succeeded"
            entry["already_tagged"] = True
            results.append(entry)
            continue
        db.session.add(
            DocumentLabel(
                document_id=doc.id,
                organization_id=doc.organization_id,
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
            jsonify(label=label, succeeded=0, failed=failed, results=results),
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


@document_label_api.route("/bulk/label/remove", methods=["POST"])
@jwt_required()
def bulk_untag_documents():
    """Detach a label from up to 100 documents atomically.

    Payload: ``{"document_ids": [int, ...], "label": "<str>"}``.
    Rows that do not carry the label report ``succeeded`` with
    ``already_removed=True``.
    """
    user = _actor()
    data = _payload()
    ids = data.get("document_ids")
    label_raw = data.get("label")
    if not isinstance(ids, list) or not ids:
        abort(400, description="document_ids_required")
    if len(ids) > 100:
        abort(413, description="bulk_label_remove_limit_100")
    label = _normalise_label(label_raw)
    if label is None:
        abort(400, description="label_invalid")

    seen: set[int] = set()
    results: list[dict] = []
    removed = 0
    for doc_id in ids:
        entry = {"document_id": doc_id}
        if type(doc_id) is not int:
            entry["status"] = "failed"
            entry["error_code"] = "document_id_invalid"
            results.append(entry)
            continue
        if doc_id in seen:
            entry["status"] = "failed"
            entry["error_code"] = "duplicate_id"
            results.append(entry)
            continue
        seen.add(doc_id)
        doc = Document.query.filter_by(
            id=doc_id,
            organization_id=user.organization_id,
            created_by=user.id,
            deleted_at=None,
        ).first()
        if doc is None:
            entry["status"] = "failed"
            entry["error_code"] = "document_not_found"
            results.append(entry)
            continue
        row = DocumentLabel.query.filter_by(
            document_id=doc.id, label=label
        ).first()
        if row is None:
            entry["status"] = "succeeded"
            entry["already_removed"] = True
            results.append(entry)
            continue
        db.session.delete(row)
        removed += 1
        entry["status"] = "succeeded"
        entry["already_removed"] = False
        results.append(entry)

    succeeded = sum(1 for r in results if r["status"] == "succeeded")
    failed = len(results) - succeeded
    if succeeded == 0:
        db.session.rollback()
        return (
            jsonify(label=label, succeeded=0, failed=failed, results=results),
            400,
        )
    db.session.commit()
    http_status = 207 if failed else 200
    return (
        jsonify(
            label=label,
            succeeded=succeeded,
            failed=failed,
            removed=removed,
            results=results,
        ),
        http_status,
    )
