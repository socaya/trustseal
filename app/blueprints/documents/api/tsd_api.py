"""TRUSTSEAL proprietary document (.tsd) API.

* ``GET  /api/tsd/``            — list the current tenant's TSDs (no content).
* ``POST /api/tsd/``            — create a new TSD from editor content.
* ``GET  /api/tsd/<id>``        — metadata for one TSD.
* ``GET  /api/tsd/<id>/content``— decrypted content envelope (for the editor).
* ``PUT  /api/tsd/<id>``        — update content; requires ``If-Match: <version>``.
* ``GET  /api/tsd/<id>/download``— the raw encrypted .tsd container bytes.
* ``DELETE /api/tsd/<id>``      — soft delete.

All routes require a session-authenticated user and scope to the
caller's organization. Decrypted content never crosses the tenant
boundary.
"""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, Response, abort, jsonify, request
from flask_login import current_user, login_required

from app.extensions import db
from app.models.tsd_document import EXPORT_POLICIES, TSD_STATUSES, TSDocument
from app.services.tsd_format import (
    TSDError,
    decrypt_content_envelope,
    encrypt_content_envelope,
    pack_content,
    serialize_container,
    sha256_hex,
)
from app.services.tsd_ingest import SUPPORTED_SUFFIXES, IngestError, ingest


tsd_api = Blueprint("tsd_api", __name__, url_prefix="/api/tsd")


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
    return jsonify([r.to_dict() for r in rows])


# ============================================================ create


@tsd_api.route("/", methods=["POST"])
@login_required
def create_tsd():
    actor = _actor()
    payload = request.get_json(silent=True) or {}

    title = (payload.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title_required"}), 400

    html = payload.get("content_html") or ""
    description = (payload.get("description") or "").strip() or None
    tags_raw = payload.get("tags") or ""
    if isinstance(tags_raw, str):
        tags_list = [t.strip() for t in tags_raw.split(",") if t.strip()]
        tags_db = ",".join(tags_list) or None
    elif isinstance(tags_raw, list):
        tags_list = [str(t).strip() for t in tags_raw if str(t).strip()]
        tags_db = ",".join(tags_list) or None
    else:
        return jsonify({"error": "tags_must_be_string_or_list"}), 400

    export_policy = payload.get("export_policy", "pdf_allowed")
    if export_policy not in EXPORT_POLICIES:
        return jsonify({"error": "invalid_export_policy"}), 400

    try:
        plaintext = pack_content(html=html, description=description, tags=tags_list)
        ciphertext = encrypt_content_envelope(
            plaintext, organization_id=actor.organization_id
        )
    except TSDError as exc:
        return jsonify({"error": "encrypt_failed", "message": str(exc)}), 400

    row = TSDocument(
        organization_id=actor.organization_id,
        created_by_id=actor.id,
        title=title[:255],
        description=description[:1000] if description else None,
        tags=tags_db,
        export_policy=export_policy,
        status="draft",
        ciphertext=ciphertext,
        ciphertext_sha256=sha256_hex(ciphertext),
        plaintext_bytes=len(plaintext),
    )
    db.session.add(row)
    db.session.commit()
    return jsonify(row.to_dict()), 201


# ============================================================ metadata / content


@tsd_api.route("/<int:tsd_id>", methods=["GET"])
@login_required
def get_tsd(tsd_id: int):
    row = _owned(tsd_id)
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
        return jsonify({"error": "decrypt_failed", "message": str(exc)}), 500
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
        return jsonify({
            "error": "version_conflict",
            "current_version": row.version,
        }), 412

    payload = request.get_json(silent=True) or {}

    if "title" in payload:
        title = (payload.get("title") or "").strip()
        if not title:
            return jsonify({"error": "title_required"}), 400
        row.title = title[:255]

    if "description" in payload:
        description = (payload.get("description") or "").strip() or None
        row.description = description[:1000] if description else None

    if "export_policy" in payload:
        if payload["export_policy"] not in EXPORT_POLICIES:
            return jsonify({"error": "invalid_export_policy"}), 400
        row.export_policy = payload["export_policy"]

    if "status" in payload:
        if payload["status"] not in TSD_STATUSES:
            return jsonify({"error": "invalid_status"}), 400
        row.status = payload["status"]

    if "tags" in payload:
        tags_raw = payload.get("tags") or ""
        if isinstance(tags_raw, str):
            tags_list = [t.strip() for t in tags_raw.split(",") if t.strip()]
        elif isinstance(tags_raw, list):
            tags_list = [str(t).strip() for t in tags_raw if str(t).strip()]
        else:
            return jsonify({"error": "tags_must_be_string_or_list"}), 400
        row.tags = ",".join(tags_list) or None
    else:
        tags_list = [t.strip() for t in (row.tags or "").split(",") if t.strip()]

    if "content_html" in payload:
        try:
            plaintext = pack_content(
                html=payload.get("content_html") or "",
                description=row.description,
                tags=tags_list,
            )
            ciphertext = encrypt_content_envelope(
                plaintext, organization_id=row.organization_id
            )
        except TSDError as exc:
            return jsonify({"error": "encrypt_failed", "message": str(exc)}), 400
        row.ciphertext = ciphertext
        row.ciphertext_sha256 = sha256_hex(ciphertext)
        row.plaintext_bytes = len(plaintext)

    row.version += 1
    row.updated_at = datetime.utcnow()
    db.session.commit()
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
    """Accept a PDF / DOCX / XLSX / TXT / HTML upload and store it as a TSD.

    multipart/form-data:
        file           — the upload
        title          — optional override; defaults to the filename stem
        export_policy  — "pdf_allowed" (default) or "encrypted_only"
    """
    actor = _actor()

    f = request.files.get("file")
    if f is None or not f.filename:
        return jsonify({"error": "file_required"}), 400

    try:
        html, meta = ingest(f.filename, f.stream)
    except IngestError as exc:
        return jsonify({"error": "ingest_failed", "message": str(exc)}), 400

    title = (request.form.get("title") or "").strip()
    if not title:
        from os.path import splitext
        title = splitext(f.filename)[0] or "Untitled"
    export_policy = request.form.get("export_policy", "pdf_allowed")
    if export_policy not in EXPORT_POLICIES:
        return jsonify({"error": "invalid_export_policy"}), 400

    try:
        plaintext = pack_content(
            html=html,
            description=f"Imported from {f.filename} ({meta.get('source_type')})",
            tags=[meta.get("source_type", "upload")],
            extras={"source_file": f.filename, **meta},
        )
        ciphertext = encrypt_content_envelope(
            plaintext, organization_id=actor.organization_id
        )
    except TSDError as exc:
        return jsonify({"error": "encrypt_failed", "message": str(exc)}), 400

    row = TSDocument(
        organization_id=actor.organization_id,
        created_by_id=actor.id,
        title=title[:255],
        description=f"Imported from {f.filename}"[:1000],
        tags=meta.get("source_type", "upload"),
        export_policy=export_policy,
        status="draft",
        ciphertext=ciphertext,
        ciphertext_sha256=sha256_hex(ciphertext),
        plaintext_bytes=len(plaintext),
    )
    db.session.add(row)
    db.session.commit()
    return jsonify(row.to_dict()), 201


# ============================================================ delete


@tsd_api.route("/<int:tsd_id>", methods=["DELETE"])
@login_required
def delete_tsd(tsd_id: int):
    row = _owned(tsd_id)
    row.deleted_at = datetime.utcnow()
    db.session.commit()
    return "", 204
