"""Tenant-aware document metadata endpoints.

The legacy document API contained placeholder CRUD methods. These endpoints
intentionally manage draft metadata only; evidence and signed records must be
handled by immutable document workflows, not generic CRUD.
"""
import io
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
    db.session.flush()
    from app.services.event_delivery import enqueue
    enqueue(
        event_type="document.draft.created", aggregate_type="document",
        aggregate_id=doc.id, organization_id=doc.organization_id,
        actor_id=user.id, action="document.draft.created",
        idempotency_key="document-created:%s" % doc.id,
    )
    db.session.commit()
    return jsonify(_serialize(doc)), 201


@document_api.route("/<int:document_id>/", methods=["PUT"])
@jwt_required()
def update_document(document_id):
    # Lock before reading the revision so concurrent edits cannot overwrite
    # each other or reuse the same outbox idempotency key.
    user = actor()
    doc = Document.query.filter(
        Document.id == document_id,
        Document.created_by == user.id,
        Document.deleted_at.is_(None),
    ).with_for_update().first()
    if doc is None:
        abort(404)
    if (doc.status or "").lower() != "draft":
        abort(409, description="Only drafts are editable")
    data = _payload()
    expected = data.pop("expected_version", None)
    if type(expected) is not int or expected < 1:
        abort(428, description="expected_version integer required")
    if expected != (doc.version or 1):
        abort(409, description="Document revision conflict")
    if not data or set(data) - EDITABLE:
        abort(400, description="Only editable draft fields are accepted")
    _validate(data)
    for key in EDITABLE:
        if key in data:
            setattr(doc, key, data[key].strip() if key == "title" else data[key])
    doc.last_modified_by_id = user.id
    doc.version = expected + 1
    from app.services.event_delivery import enqueue
    enqueue(
        event_type="document.draft.updated", aggregate_type="document",
        aggregate_id=doc.id, organization_id=doc.organization_id,
        actor_id=user.id, action="document.draft.updated",
        idempotency_key="document-updated:%s:%s" % (doc.id, doc.version),
    )
    db.session.commit()
    return jsonify(_serialize(doc))


@document_api.route("/<int:document_id>/", methods=["DELETE"])
@jwt_required()
def delete_document(document_id):
    user = actor()
    doc = Document.query.filter(
        Document.id == document_id,
        Document.created_by == user.id,
        Document.deleted_at.is_(None),
    ).with_for_update().first()
    if doc is None:
        abort(404)
    if (doc.status or "").lower() != "draft":
        abort(409, description="Non-draft documents cannot be deleted")
    expected = request.headers.get("If-Match")
    if expected is None or not expected.isdecimal():
        abort(428, description="Numeric If-Match revision required")
    if int(expected) != (doc.version or 1):
        abort(409, description="Document revision conflict")
    doc.deleted_at = datetime.utcnow()
    from app.services.event_delivery import enqueue
    enqueue(
        event_type="document.draft.deleted", aggregate_type="document",
        aggregate_id=doc.id, organization_id=doc.organization_id,
        actor_id=user.id, action="document.draft.deleted",
        idempotency_key="document-deleted:%s" % doc.id,
    )
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
    from app.services.event_delivery import enqueue
    enqueue(
        event_type="document.snapshot.created", aggregate_type="document",
        aggregate_id=doc.id, organization_id=doc.organization_id,
        actor_id=user.id, action="document.snapshot.created",
        idempotency_key="document-snapshot:%s:%s" % (doc.id, revision),
    )
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


# === Private, scanned document file objects ===
def _blob_metadata(record):
    return {
        "id": record.id,
        "document_id": record.document_id,
        "revision": record.revision,
        "file_name": record.file_name,
        "file_size": record.file_size,
        "mime_type": record.mime_type,
        "sha256": record.sha256,
        "created_by_id": record.created_by_id,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "security_status": "scanned_private_object",
    }


@document_api.route("/search", methods=["GET"])
@jwt_required()
def search_documents():
    """Tenant-scoped full-text search over title + description.

    ``?q=`` — the query string. ``?limit=`` — optional result cap
    (default 50, max 200). Results ranked by ``ts_rank`` and
    always scoped to the caller's own organization.
    """
    from app.services.document_search import DEFAULT_LIMIT, search

    user = actor()
    q = request.args.get("q", "")
    try:
        limit = int(request.args.get("limit", DEFAULT_LIMIT))
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    hits = search(user.organization_id, q, limit=limit)
    return jsonify(
        hits=[
            {
                "document_id": h.document_id,
                "title": h.title,
                "description": h.description,
                "status": h.status,
                "created_at": h.created_at,
                "rank": h.rank,
            }
            for h in hits
        ],
        count=len(hits),
        query=q,
    )


@document_api.route("/bulk", methods=["POST"])
@jwt_required()
def bulk_ingest_documents():
    """Ingest up to 25 PDF files in a single request.

    Each file lands as its own ``Document`` + ``DocumentBlob`` pair.
    Per-file failures do not fail sibling files; the response reports
    a ``succeeded`` / ``failed`` status per item plus an overall
    batch summary. Failed items record a machine-readable ``error_code``
    and a short human message.

    Pre-existing per-file ingestion rules still apply — PDF header
    check, scanner, size cap.
    """
    from datetime import datetime as _dt

    from flask import current_app
    from sqlalchemy import func

    from app.models.bulk_ingest import BulkIngestBatch, BulkIngestItem
    from app.models.documents.document import Document
    from app.models.documents.document_activity import DocumentActivity
    from app.models.documents.document_blob import DocumentBlob
    from app.services.documents.private_storage import (
        IngestionError, cleanup_object, store_scanned_pdf,
    )
    from app.services.event_delivery import enqueue

    user = actor()
    uploads = request.files.getlist("files")
    if not uploads:
        abort(400, description="multipart/form-data files field required")
    if len(uploads) > 25:
        abort(413, description="bulk_limit_exceeded_25_files")

    batch = BulkIngestBatch(
        organization_id=user.organization_id,
        created_by_id=user.id,
        item_count=len(uploads),
    )
    db.session.add(batch)
    db.session.flush()
    results = []
    for upload in uploads:
        source_name = (
            upload.filename or "upload.pdf"
        ).replace("\\", "/").split("/")[-1][:200]
        item = BulkIngestItem(
            batch_id=batch.id,
            filename=source_name,
            status="pending",
        )
        db.session.add(item)
        db.session.flush()
        doc = Document(
            title=source_name,
            status="draft",
            created_by=user.id,
            organization_id=user.organization_id,
        )
        db.session.add(doc)
        try:
            db.session.flush()
        except Exception as exc:  # pragma: no cover - defensive
            db.session.rollback()
            db.session.add(item)
            item.status = "failed"
            item.error_code = "document_create_failed"
            item.error_message = str(exc)[:400]
            item.completed_at = _dt.utcnow()
            db.session.flush()
            results.append(item)
            continue
        key = None
        try:
            key, name, size, digest, scanner = store_scanned_pdf(
                upload.stream, source_name, current_app.config
            )
            blob = DocumentBlob(
                document_id=doc.id,
                revision=1,
                object_key=key,
                file_name=name,
                mime_type="application/pdf",
                file_size=size,
                sha256=digest,
                scanner=scanner,
                created_by_id=user.id,
            )
            db.session.add(blob)
            db.session.flush()
            db.session.add(
                DocumentActivity(
                    document_id=doc.id,
                    user_id=user.id,
                    activity_type="private_file_ingested",
                    details="Bulk-ingest PDF revision 1, SHA-256 %s" % digest,
                )
            )
            enqueue(
                event_type="document.file.ingested",
                aggregate_type="document",
                aggregate_id=doc.id,
                organization_id=doc.organization_id,
                actor_id=user.id,
                action="document.file.ingested",
                idempotency_key="document-file:%s:1" % doc.id,
            )
            item.status = "succeeded"
            item.document_id = doc.id
            item.blob_id = blob.id
            item.completed_at = _dt.utcnow()
        except IngestionError as exc:
            # The per-file failure must not poison the batch — the
            # Document row rolls back along with the half-created blob,
            # but the item + batch rows persist so the client has a
            # durable record of the failure.
            db.session.rollback()
            if key:
                try:
                    cleanup_object(key, current_app.config)
                except IngestionError:
                    current_app.logger.exception(
                        "Unable to clean orphaned bulk-ingest object"
                    )
            # Re-fetch the batch + item that just got rolled back along
            # with the failed Document insert.
            batch = db.session.get(BulkIngestBatch, batch.id) or BulkIngestBatch(
                id=batch.id,
                organization_id=user.organization_id,
                created_by_id=user.id,
                item_count=len(uploads),
            )
            if db.session.get(BulkIngestBatch, batch.id) is None:
                db.session.add(batch)
                db.session.flush()
            item = BulkIngestItem(
                batch_id=batch.id,
                filename=source_name,
                status="failed",
                error_code="ingestion_error",
                error_message=str(exc)[:400],
                completed_at=_dt.utcnow(),
            )
            db.session.add(item)
            db.session.flush()
        results.append(item)
    batch.success_count = sum(1 for r in results if r.status == "succeeded")
    batch.failure_count = sum(1 for r in results if r.status == "failed")
    batch.completed_at = _dt.utcnow()
    # Meter one hit per successful item, deduplicated by item id so
    # the same batch cannot be re-metered on retry.
    from app.services import usage_ledger as _usage

    for r in results:
        if r.status != "succeeded":
            continue
        _usage.record(
            user.organization_id,
            "document.bulk_ingested",
            f"bulk_item:{r.id}",
            actor_id=user.id,
        )
    db.session.commit()

    def _item_payload(it):
        return {
            "id": it.id,
            "filename": it.filename,
            "status": it.status,
            "document_id": it.document_id,
            "blob_id": it.blob_id,
            "error_code": it.error_code,
            "error_message": it.error_message,
        }

    response = jsonify(
        batch={
            "id": batch.id,
            "item_count": batch.item_count,
            "success_count": batch.success_count,
            "failure_count": batch.failure_count,
            "created_at": batch.created_at.isoformat(),
            "completed_at": batch.completed_at.isoformat(),
        },
        items=[_item_payload(it) for it in results],
    )
    response.status_code = 207 if batch.failure_count else 201
    response.headers["Cache-Control"] = "no-store"
    return response


@document_api.route("/bulk/<int:batch_id>", methods=["GET"])
@jwt_required()
def bulk_ingest_status(batch_id):
    """Return the recorded batch and its items for polling retries."""
    from app.models.bulk_ingest import BulkIngestBatch

    user = actor()
    batch = BulkIngestBatch.query.filter_by(
        id=batch_id, organization_id=user.organization_id
    ).first()
    if batch is None:
        abort(404)
    return jsonify(
        batch={
            "id": batch.id,
            "item_count": batch.item_count,
            "success_count": batch.success_count,
            "failure_count": batch.failure_count,
            "created_at": batch.created_at.isoformat(),
            "completed_at": batch.completed_at.isoformat()
            if batch.completed_at
            else None,
        },
        items=[
            {
                "id": it.id,
                "filename": it.filename,
                "status": it.status,
                "document_id": it.document_id,
                "blob_id": it.blob_id,
                "error_code": it.error_code,
                "error_message": it.error_message,
            }
            for it in batch.items
        ],
    )


@document_api.route(
    "/<int:document_id>/blobs/<int:blob_id>/preview", methods=["GET"]
)
@jwt_required()
def preview_document_blob(document_id, blob_id):
    """Return a sanitised copy of the stored PDF for in-browser preview.

    The service strips document-level OpenAction + additional
    actions, named /JS destinations, embedded files, and per-page /AA
    before serving the bytes. The feature is gated by
    ``SAFE_PREVIEW_ENABLED`` so an operator can keep the raw-download
    pipeline authoritative until a jurisdictional review signs off on
    the sanitiser's completeness.
    """
    from flask import current_app, send_file

    from app.models.documents.document_blob import DocumentBlob
    from app.services.documents.private_storage import (
        IngestionError, object_path,
    )
    from app.services.documents.safe_preview import (
        SafePreviewError, enabled, sanitize,
    )

    user = actor()
    doc = Document.query.filter(
        Document.id == document_id,
        db.or_(
            Document.created_by == user.id,
            Document.organization_id == user.organization_id,
        ),
        Document.deleted_at.is_(None),
    ).first()
    if doc is None:
        abort(404)
    blob = DocumentBlob.query.filter_by(id=blob_id, document_id=doc.id).first()
    if blob is None:
        abort(404)
    if not enabled(current_app.config):
        abort(503, description="safe_preview_disabled")
    try:
        path = object_path(blob.object_key, current_app.config)
    except IngestionError:
        abort(503, description="preview_unavailable")
    try:
        sanitized = sanitize(path.read_bytes())
    except SafePreviewError as exc:
        abort(422, description=str(exc))
    response = send_file(
        io.BytesIO(sanitized),
        mimetype="application/pdf",
        as_attachment=False,
        download_name=f"{blob.file_name.rsplit('.', 1)[0]}-preview.pdf",
        conditional=False,
        etag=False,
        max_age=0,
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Disposition"] = (
        f'inline; filename="{blob.file_name.rsplit(".", 1)[0]}-preview.pdf"'
    )
    return response


@document_api.route("/<int:document_id>/images", methods=["POST"])
@jwt_required()
def ingest_document_image(document_id):
    """Owner-only; convert a PNG/JPEG upload to PDF and ingest it.

    Reuses the same scanner + manifest invariants as PDF ingestion.
    The feature is gated by ``IMAGE_PDF_CONVERSION_ENABLED`` so an
    operator can keep it disabled until a jurisdiction-specific
    acceptance test passes.
    """
    import io

    from flask import current_app
    from sqlalchemy import func
    from app.models.documents.document_blob import DocumentBlob
    from app.models.documents.document_activity import DocumentActivity
    from app.services.documents.image_conversion import (
        ImageConversionError,
        convert_to_pdf,
        detect_format,
    )
    from app.services.documents.private_storage import (
        IngestionError, cleanup_object, store_scanned_pdf,
    )

    user = actor()
    doc = Document.query.filter(
        Document.id == document_id,
        Document.created_by == user.id,
        Document.deleted_at.is_(None),
    ).with_for_update().first()
    if doc is None:
        abort(404)
    if (doc.status or "").lower() != "draft":
        abort(409, description="Only drafts accept uploaded documents")
    incoming = request.files.get("file")
    if incoming is None:
        abort(400, description="multipart/form-data file field required")
    if len(request.files) != 1:
        abort(400, description="Exactly one file is required")
    source_name = (incoming.filename or "image").replace("\\", "/").split("/")[-1]
    image_bytes = incoming.stream.read()
    try:
        source_format = detect_format(image_bytes)
        pdf_bytes = convert_to_pdf(image_bytes, config=current_app.config)
    except ImageConversionError as exc:
        abort(400, description=str(exc))
    stem = source_name.rsplit(".", 1)[0] or "image"
    pdf_name = f"{stem}.pdf"
    key = None
    try:
        key, name, size, digest, scanner = store_scanned_pdf(
            io.BytesIO(pdf_bytes), pdf_name, current_app.config
        )
        revision = (db.session.query(func.max(DocumentBlob.revision))
                    .filter(DocumentBlob.document_id == doc.id).scalar() or 0) + 1
        record = DocumentBlob(
            document_id=doc.id,
            revision=revision,
            object_key=key,
            file_name=name,
            mime_type="application/pdf",
            file_size=size,
            sha256=digest,
            scanner=scanner,
            created_by_id=user.id,
        )
        db.session.add(record)
        from app.services.event_delivery import enqueue
        enqueue(
            event_type="document.image.ingested", aggregate_type="document",
            aggregate_id=doc.id, organization_id=doc.organization_id,
            actor_id=user.id, action="document.image.ingested",
            idempotency_key="document-image:%s:%s" % (doc.id, revision),
        )
        db.session.add(DocumentActivity(
            document_id=doc.id, user_id=user.id,
            activity_type="private_image_converted",
            details=(
                "Converted %s %s to PDF revision %s, SHA-256 %s"
                % (source_format.upper(), source_name, revision, digest)
            ),
        ))
        db.session.commit()
    except IngestionError as exc:
        db.session.rollback()
        abort(422, description=str(exc))
    except Exception:
        db.session.rollback()
        if key:
            try:
                cleanup_object(key, current_app.config)
            except IngestionError:
                current_app.logger.exception("Unable to clean orphaned converted image")
        raise
    response = jsonify(_blob_metadata(record))
    response.headers["Cache-Control"] = "no-store"
    return response, 201


@document_api.route("/<int:document_id>/files", methods=["POST"])
@jwt_required()
def ingest_document_file(document_id):
    """Owner-only; immutable file attachment to a draft document."""
    from flask import current_app
    from sqlalchemy import func
    from app.models.documents.document_blob import DocumentBlob
    from app.models.documents.document_activity import DocumentActivity
    from app.services.documents.private_storage import (
        IngestionError, store_scanned_pdf, cleanup_object,
    )

    user = actor()
    doc = Document.query.filter(
        Document.id == document_id,
        Document.created_by == user.id,
        Document.deleted_at.is_(None),
    ).with_for_update().first()
    if doc is None:
        abort(404)
    if (doc.status or "").lower() != "draft":
        abort(409, description="Only drafts accept uploaded documents")
    incoming = request.files.get("file")
    if incoming is None:
        abort(400, description="multipart/form-data file field required")
    if len(request.files) != 1:
        abort(400, description="Exactly one file is required")

    key = None
    try:
        key, name, size, digest, scanner = store_scanned_pdf(
            incoming.stream, incoming.filename, current_app.config
        )
        revision = (db.session.query(func.max(DocumentBlob.revision))
                    .filter(DocumentBlob.document_id == doc.id).scalar() or 0) + 1
        record = DocumentBlob(
            document_id=doc.id,
            revision=revision,
            object_key=key,
            file_name=name,
            mime_type="application/pdf",
            file_size=size,
            sha256=digest,
            scanner=scanner,
            created_by_id=user.id,
        )
        db.session.add(record)
        from app.services.event_delivery import enqueue
        enqueue(
            event_type="document.file.ingested", aggregate_type="document",
            aggregate_id=doc.id, organization_id=doc.organization_id,
            actor_id=user.id, action="document.file.ingested",
            idempotency_key="document-file:%s:%s" % (doc.id, revision),
        )
        db.session.add(DocumentActivity(
            document_id=doc.id, user_id=user.id,
            activity_type="private_file_ingested",
            details="Private PDF revision %s, SHA-256 %s" % (revision, digest),
        ))
        db.session.commit()
    except IngestionError as exc:
        db.session.rollback()
        abort(422, description=str(exc))
    except Exception:
        db.session.rollback()
        if key:
            try:
                cleanup_object(key, current_app.config)
            except IngestionError:
                current_app.logger.exception("Unable to clean orphaned document file")
        raise
    response = jsonify(_blob_metadata(record))
    response.headers["Cache-Control"] = "no-store"
    return response, 201


@document_api.route("/<int:document_id>/files", methods=["GET"])
@jwt_required()
def list_document_files(document_id):
    from app.models.documents.document_blob import DocumentBlob
    get_authorized_document_or_abort(document_id)
    records = DocumentBlob.query.filter(
        DocumentBlob.document_id == document_id
    ).order_by(DocumentBlob.revision.desc()).limit(100).all()
    response = jsonify([_blob_metadata(record) for record in records])
    response.headers["Cache-Control"] = "no-store"
    return response


@document_api.route("/<int:document_id>/files/<int:file_id>/download", methods=["GET"])
@jwt_required()
def download_document_file(document_id, file_id):
    from flask import current_app, send_file
    from sqlalchemy import or_
    from app.models.documents.document_blob import DocumentBlob
    from app.services.documents.private_storage import IngestionError, check_object_digest

    doc = get_authorized_document_or_abort(document_id)
    user = actor()
    if doc.created_by != user.id:
        allowed = DocumentShare.query.filter(
            DocumentShare.document_id == doc.id,
            DocumentShare.shared_with_user_id == user.id,
            DocumentShare.can_view.is_(True),
            DocumentShare.can_download.is_(True),
            or_(
                DocumentShare.expires_at.is_(None),
                DocumentShare.expires_at > datetime.utcnow(),
            ),
        ).first()
        if allowed is None:
            abort(404)
    record = DocumentBlob.query.filter_by(
        id=file_id, document_id=doc.id
    ).first_or_404()
    try:
        path = check_object_digest(record.object_key, record.sha256, current_app.config)
    except IngestionError:
        current_app.logger.exception("Private object integrity or storage check failed")
        abort(503, description="Document is temporarily unavailable")
    response = send_file(
        path, mimetype=record.mime_type,
        as_attachment=True, download_name=record.file_name,
        conditional=False, etag=False, max_age=0,
    )
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# ============================================================ AE1 bulk delete


@document_api.route("/bulk/delete", methods=["POST"])
@jwt_required()
def bulk_delete_documents():
    """Soft-delete up to 100 draft documents atomically.

    Payload: ``{"document_ids": [int, ...]}``. Non-draft rows and
    rows the caller does not own report per-row ``failed`` with
    ``error_code``; already-deleted rows report ``succeeded`` with
    ``already_deleted=True``. The whole batch rolls back if every
    row fails so a bad request never half-applies.
    """
    from app.services.event_delivery import enqueue

    user = actor()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="JSON object required")
    ids = data.get("document_ids")
    if not isinstance(ids, list) or not ids:
        abort(400, description="document_ids_required")
    if len(ids) > 100:
        abort(413, description="bulk_delete_limit_100")

    seen: set[int] = set()
    results: list[dict] = []
    deleted_now = 0
    moment = datetime.utcnow()
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
        doc = (
            Document.query.filter_by(
                id=doc_id,
                created_by=user.id,
                organization_id=user.organization_id,
            )
            .with_for_update()
            .first()
        )
        if doc is None:
            entry["status"] = "failed"
            entry["error_code"] = "document_not_found"
            results.append(entry)
            continue
        if doc.deleted_at is not None:
            entry["status"] = "succeeded"
            entry["already_deleted"] = True
            results.append(entry)
            continue
        if (doc.status or "").lower() != "draft":
            entry["status"] = "failed"
            entry["error_code"] = "state_not_draft"
            results.append(entry)
            continue
        doc.deleted_at = moment
        enqueue(
            event_type="document.draft.deleted",
            aggregate_type="document",
            aggregate_id=doc.id,
            organization_id=doc.organization_id,
            actor_id=user.id,
            action="document.draft.deleted",
            idempotency_key="document-deleted:%s" % doc.id,
        )
        deleted_now += 1
        entry["status"] = "succeeded"
        entry["already_deleted"] = False
        results.append(entry)

    succeeded = sum(1 for r in results if r["status"] == "succeeded")
    failed = len(results) - succeeded
    if succeeded == 0:
        db.session.rollback()
        return (
            jsonify(succeeded=0, failed=failed, results=results),
            400,
        )
    db.session.commit()
    http_status = 207 if failed else 200
    return (
        jsonify(
            succeeded=succeeded,
            failed=failed,
            deleted=deleted_now,
            results=results,
        ),
        http_status,
    )


# ============================================================ AJ1 doc transfer


@document_api.route("/<int:document_id>/transfer", methods=["POST"])
@jwt_required()
def transfer_document(document_id):
    """Reassign a draft/pending document to another tenant member.

    Payload: ``{"new_owner_id": <int>}``. Only draft or pending
    documents are transferable; once a document reaches a signed or
    archived state the audit trail must retain the original issuer.
    The target user must be active and in the same organisation.
    """
    from app.policies.api_access import is_admin
    from app.services import operator_notifications
    from app.services.event_delivery import enqueue

    user = actor()
    doc = (
        Document.query.filter_by(
            id=document_id,
            organization_id=user.organization_id,
            deleted_at=None,
        )
        .with_for_update()
        .first()
    )
    if doc is None:
        abort(404)
    if doc.created_by != user.id and not is_admin(user.id):
        abort(403, description="transfer_requires_owner_or_admin")
    if (doc.status or "").lower() not in {"draft", "pending"}:
        abort(409, description="transfer_requires_draft_or_pending")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="JSON object required")
    new_owner_id = data.get("new_owner_id")
    if type(new_owner_id) is not int or new_owner_id <= 0:
        abort(400, description="new_owner_id_invalid")
    if new_owner_id == doc.created_by:
        return jsonify(
            document_id=doc.id,
            owner_id=doc.created_by,
            changed=False,
        ), 200
    target = db.session.get(User, new_owner_id)
    if (
        target is None
        or not target.is_active
        or target.organization_id != doc.organization_id
    ):
        abort(404, description="new_owner_not_in_tenant")
    previous = doc.created_by
    doc.created_by = target.id
    enqueue(
        event_type="document.ownership.transferred",
        aggregate_type="document",
        aggregate_id=doc.id,
        organization_id=doc.organization_id,
        actor_id=user.id,
        action="document.ownership.transferred",
        idempotency_key="document-transfer:%s:%s" % (doc.id, target.id),
    )
    operator_notifications.publish(
        organization_id=doc.organization_id,
        recipient_user_id=target.id,
        kind="document.ownership.transferred",
        subject_type="document",
        subject_id=doc.id,
        summary=(
            f"Document #{doc.id} '{doc.title}' was transferred to you "
            f"by user #{user.id}."
        ),
    )
    db.session.commit()
    return jsonify(
        document_id=doc.id,
        previous_owner_id=previous,
        owner_id=target.id,
        changed=True,
    ), 200
