"""TRUSTSEAL proprietary document (.tsd) API.

* ``GET  /api/tsd/``            — list the current tenant's TSDs (no content).
* ``POST /api/tsd/``            — create a new TSD from editor content.
* ``GET  /api/tsd/<id>``        — metadata for one TSD.
* ``GET  /api/tsd/<id>/content``— decrypted content envelope (for the editor).
* ``PUT  /api/tsd/<id>``        — update content; requires ``If-Match: <version>``.
* ``GET  /api/tsd/<id>/download``— the raw encrypted .tsd container bytes.
* ``DELETE /api/tsd/<id>``      — soft delete.
* ``POST /api/tsd/ingest``      — import PDF / DOCX / XLSX / TXT / HTML / image.

All routes require a session-authenticated user and scope to the
caller's organization. Every mutation emits a SecurityEvent for the
chained-hash audit log and bumps the ``trustseal_tsd_operations_total``
counter.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from flask import Blueprint, Response, abort, jsonify, request
from flask_login import current_user, login_required

from app.extensions import db
from app.metrics import (
    record_tsd_ingest,
    record_tsd_operation,
    record_tsd_plaintext,
)
from app.models.event_delivery import SecurityEvent
from app.models.tsd_document import EXPORT_POLICIES, TSD_STATUSES, TSDocument
from app.services.tsd_format import (
    TSDError,
    decrypt_content_envelope,
    encrypt_content_envelope,
    pack_content,
    sanitize_html,
    serialize_container,
    sha256_hex,
)
from app.services.tsd_ingest import IngestError, ingest


tsd_api = Blueprint("tsd_api", __name__, url_prefix="/api/tsd")


# ============================================================ helpers


def _actor():
    if not current_user.is_authenticated:
        abort(401)
    if current_user.organization_id is None:
        abort(403, description="organization_required")
    return current_user


def _owned(doc_id: int) -> TSDocument:
    actor = _actor()
    row = (
        TSDocument.query
        .filter(
            TSDocument.id == doc_id,
            TSDocument.organization_id == actor.organization_id,
            TSDocument.deleted_at.is_(None),
        )
        .first()
    )
    if row is None:
        abort(404)
    return row


def _emit(
    *,
    actor_id: int,
    organization_id: int,
    action: str,
    resource_id: int,
    outcome: str = "success",
) -> None:
    """Append a SecurityEvent for the chained-hash audit log."""
    db.session.add(SecurityEvent(
        organization_id=organization_id,
        actor_id=actor_id,
        action=action,
        resource_type="ts_document",
        resource_id=resource_id,
        outcome=outcome,
        correlation_id=uuid.uuid4().hex,
    ))


def _normalise_tags(raw):
    if not raw:
        return [], None
    if isinstance(raw, str):
        tags = [t.strip() for t in raw.split(",") if t.strip()]
    elif isinstance(raw, list):
        tags = [str(t).strip() for t in raw if str(t).strip()]
    else:
        raise ValueError("tags_must_be_string_or_list")
    return tags, (",".join(tags) or None)


# ============================================================ list


@tsd_api.route("/", methods=["GET"])
@login_required
def list_tsd():
    actor = _actor()
    rows = (
        TSDocument.query
        .filter(
            TSDocument.organization_id == actor.organization_id,
            TSDocument.deleted_at.is_(None),
        )
        .order_by(TSDocument.updated_at.desc())
        .all()
    )
    record_tsd_operation("list")
    return jsonify([r.to_dict() for r in rows])


# ============================================================ create


@tsd_api.route("/", methods=["POST"])
@login_required
def create_tsd():
    actor = _actor()
    payload = request.get_json(silent=True) or {}

    title = (payload.get("title") or "").strip()
    if not title:
        record_tsd_operation("create", "invalid")
        return jsonify({"error": "title_required"}), 400
    if len(title) > 255:
        record_tsd_operation("create", "invalid")
        return jsonify({"error": "title_too_long", "max": 255}), 400

    description = (payload.get("description") or "").strip() or None
    if description and len(description) > 1000:
        record_tsd_operation("create", "invalid")
        return jsonify({"error": "description_too_long", "max": 1000}), 400

    try:
        tags_list, tags_db = _normalise_tags(payload.get("tags"))
    except ValueError as exc:
        record_tsd_operation("create", "invalid")
        return jsonify({"error": str(exc)}), 400

    export_policy = payload.get("export_policy", "pdf_allowed")
    if export_policy not in EXPORT_POLICIES:
        record_tsd_operation("create", "invalid")
        return jsonify({"error": "invalid_export_policy"}), 400

    safe_html = sanitize_html(payload.get("content_html") or "")

    try:
        plaintext = pack_content(html=safe_html, description=description, tags=tags_list)
        ciphertext = encrypt_content_envelope(
            plaintext, organization_id=actor.organization_id
        )
    except TSDError as exc:
        record_tsd_operation("create", "encrypt_failed")
        return jsonify({"error": "encrypt_failed", "message": str(exc)}), 400

    row = TSDocument(
        organization_id=actor.organization_id,
        created_by_id=actor.id,
        title=title,
        description=description,
        tags=tags_db,
        export_policy=export_policy,
        status="draft",
        ciphertext=ciphertext,
        ciphertext_sha256=sha256_hex(ciphertext),
        plaintext_bytes=len(plaintext),
    )
    db.session.add(row)
    db.session.flush()
    _emit(actor_id=actor.id, organization_id=actor.organization_id,
          action="tsd.create", resource_id=row.id)
    db.session.commit()

    record_tsd_operation("create")
    record_tsd_plaintext(len(plaintext))
    return jsonify(row.to_dict()), 201


# ============================================================ metadata / content


@tsd_api.route("/<int:tsd_id>", methods=["GET"])
@login_required
def get_tsd(tsd_id: int):
    row = _owned(tsd_id)
    record_tsd_operation("get_metadata")
    return jsonify(row.to_dict())


@tsd_api.route("/<int:tsd_id>/content", methods=["GET"])
@login_required
def get_tsd_content(tsd_id: int):
    row = _owned(tsd_id)
    try:
        content = decrypt_content_envelope(
            row.ciphertext, organization_id=row.organization_id
        )
    except TSDError as exc:
        _emit(actor_id=current_user.id, organization_id=row.organization_id,
              action="tsd.open", resource_id=row.id, outcome="decrypt_failed")
        db.session.commit()
        record_tsd_operation("open", "decrypt_failed")
        return jsonify({"error": "decrypt_failed", "message": str(exc)}), 500

    _emit(actor_id=current_user.id, organization_id=row.organization_id,
          action="tsd.open", resource_id=row.id)
    db.session.commit()
    record_tsd_operation("open")

    meta = row.to_dict()
    meta["content"] = content
    return jsonify(meta)


# ============================================================ update


@tsd_api.route("/<int:tsd_id>", methods=["PUT"])
@login_required
def update_tsd(tsd_id: int):
    row = _owned(tsd_id)

    if_match = request.headers.get("If-Match", "").strip('"')
    if if_match and if_match != str(row.version):
        record_tsd_operation("update", "version_conflict")
        return jsonify({
            "error": "version_conflict",
            "current_version": row.version,
        }), 412

    payload = request.get_json(silent=True) or {}

    if "title" in payload:
        title = (payload.get("title") or "").strip()
        if not title:
            record_tsd_operation("update", "invalid")
            return jsonify({"error": "title_required"}), 400
        if len(title) > 255:
            record_tsd_operation("update", "invalid")
            return jsonify({"error": "title_too_long", "max": 255}), 400
        row.title = title

    if "description" in payload:
        description = (payload.get("description") or "").strip() or None
        if description and len(description) > 1000:
            record_tsd_operation("update", "invalid")
            return jsonify({"error": "description_too_long", "max": 1000}), 400
        row.description = description

    if "export_policy" in payload:
        if payload["export_policy"] not in EXPORT_POLICIES:
            record_tsd_operation("update", "invalid")
            return jsonify({"error": "invalid_export_policy"}), 400
        row.export_policy = payload["export_policy"]

    if "status" in payload:
        if payload["status"] not in TSD_STATUSES:
            record_tsd_operation("update", "invalid")
            return jsonify({"error": "invalid_status"}), 400
        row.status = payload["status"]

    if "tags" in payload:
        try:
            tags_list, tags_db = _normalise_tags(payload.get("tags"))
        except ValueError as exc:
            record_tsd_operation("update", "invalid")
            return jsonify({"error": str(exc)}), 400
        row.tags = tags_db
    else:
        tags_list = [t.strip() for t in (row.tags or "").split(",") if t.strip()]

    if "content_html" in payload:
        safe_html = sanitize_html(payload.get("content_html") or "")
        try:
            plaintext = pack_content(
                html=safe_html,
                description=row.description,
                tags=tags_list,
            )
            ciphertext = encrypt_content_envelope(
                plaintext, organization_id=row.organization_id
            )
        except TSDError as exc:
            record_tsd_operation("update", "encrypt_failed")
            return jsonify({"error": "encrypt_failed", "message": str(exc)}), 400
        row.ciphertext = ciphertext
        row.ciphertext_sha256 = sha256_hex(ciphertext)
        row.plaintext_bytes = len(plaintext)
        record_tsd_plaintext(len(plaintext))

    row.version += 1
    row.updated_at = datetime.utcnow()
    _emit(actor_id=current_user.id, organization_id=row.organization_id,
          action="tsd.update", resource_id=row.id)
    db.session.commit()
    record_tsd_operation("update")
    return jsonify(row.to_dict())


# ============================================================ download


@tsd_api.route("/<int:tsd_id>/download", methods=["GET"])
@login_required
def download_tsd(tsd_id: int):
    row = _owned(tsd_id)
    blob = serialize_container(
        organization_id=row.organization_id,
        document_id=row.id,
        document_version=row.version,
        title=row.title,
        created_by_id=row.created_by_id,
        created_at=row.created_at,
        ciphertext=row.ciphertext,
        export_policy=row.export_policy,
    )
    _emit(actor_id=current_user.id, organization_id=row.organization_id,
          action="tsd.download", resource_id=row.id)
    db.session.commit()
    record_tsd_operation("download")

    safe_title = "".join(c for c in row.title if c.isalnum() or c in ("-", "_", " ")).strip() or "document"
    return Response(
        blob,
        mimetype="application/vnd.trustseal.doc",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_title}.tsd"',
            "X-TrustSeal-Document-Id": str(row.id),
            "X-TrustSeal-Document-Version": str(row.version),
        },
    )


# ============================================================ ingest upload


@tsd_api.route("/ingest", methods=["POST"])
@login_required
def ingest_tsd():
    """Upload a PDF / DOCX / XLSX / TXT / HTML / image → stored as TSD."""
    actor = _actor()

    f = request.files.get("file")
    if f is None or not f.filename:
        record_tsd_ingest("unknown", "invalid")
        return jsonify({"error": "file_required"}), 400

    try:
        raw_html, meta = ingest(f.filename, f.stream)
    except IngestError as exc:
        record_tsd_ingest("unknown", "ingest_failed")
        return jsonify({"error": "ingest_failed", "message": str(exc)}), 400

    safe_html = sanitize_html(raw_html)

    title = (request.form.get("title") or "").strip()
    if not title:
        from os.path import splitext
        title = splitext(f.filename)[0] or "Untitled"
    title = title[:255]

    export_policy = request.form.get("export_policy", "pdf_allowed")
    if export_policy not in EXPORT_POLICIES:
        record_tsd_ingest(meta.get("source_type", "unknown"), "invalid")
        return jsonify({"error": "invalid_export_policy"}), 400

    try:
        plaintext = pack_content(
            html=safe_html,
            description=f"Imported from {f.filename} ({meta.get('source_type')})",
            tags=[meta.get("source_type", "upload")],
            extras={"source_file": f.filename, **meta},
        )
        ciphertext = encrypt_content_envelope(
            plaintext, organization_id=actor.organization_id
        )
    except TSDError as exc:
        record_tsd_ingest(meta.get("source_type", "unknown"), "encrypt_failed")
        return jsonify({"error": "encrypt_failed", "message": str(exc)}), 400

    row = TSDocument(
        organization_id=actor.organization_id,
        created_by_id=actor.id,
        title=title,
        description=f"Imported from {f.filename}"[:1000],
        tags=meta.get("source_type", "upload"),
        export_policy=export_policy,
        status="draft",
        ciphertext=ciphertext,
        ciphertext_sha256=sha256_hex(ciphertext),
        plaintext_bytes=len(plaintext),
    )
    db.session.add(row)
    db.session.flush()
    _emit(actor_id=actor.id, organization_id=actor.organization_id,
          action="tsd.ingest", resource_id=row.id)
    db.session.commit()

    record_tsd_ingest(meta.get("source_type", "unknown"))
    record_tsd_plaintext(len(plaintext))
    return jsonify(row.to_dict()), 201


# ============================================================ delete


@tsd_api.route("/<int:tsd_id>", methods=["DELETE"])
@login_required
def delete_tsd(tsd_id: int):
    row = _owned(tsd_id)

    if_match = request.headers.get("If-Match", "").strip('"')
    if if_match and if_match != str(row.version):
        record_tsd_operation("delete", "version_conflict")
        return jsonify({
            "error": "version_conflict",
            "current_version": row.version,
        }), 412

    row.deleted_at = datetime.utcnow()
    _emit(actor_id=current_user.id, organization_id=row.organization_id,
          action="tsd.delete", resource_id=row.id)
    db.session.commit()
    record_tsd_operation("delete")
    return "", 204
