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
from datetime import datetime, timedelta

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
from app.models.tsd_document_version import TSDocumentVersion
from app.models.tsd_share import TSD_SHARE_PERMISSIONS, TSDShare
from app.models.tsd_external_share import (
    EXTERNAL_SHARE_PERMISSIONS, TSDExternalShare, hash_token, new_token,
)
from app.models.tsd_comment import TSDComment
from app.models.tsd_approval import APPROVAL_DECISIONS, TSDApproval
from app.models.tsd_presence import TSDPresence
from app.models.user import User
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
from app.services.tsd_pdf import PdfExportError, render_html_to_pdf
from app.services import tsd_templates


tsd_api = Blueprint("tsd_api", __name__, url_prefix="/api/tsd")


# ============================================================ helpers


def _actor():
    if not current_user.is_authenticated:
        abort(401)
    if current_user.organization_id is None:
        abort(403, description="organization_required")
    return current_user


def _owned(doc_id: int) -> TSDocument:
    """Fetch a TSD if the caller owns it OR has an active share grant.

    Owner = any user in the same organization (tenant-scoped).
    Grantee = user with an unrevoked, unexpired TSDShare row.
    """
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
    if row is not None:
        return row
    # Fall back to a share grant (same tenant, same user, still active).
    row = (
        TSDocument.query
        .join(TSDShare, TSDShare.tsd_id == TSDocument.id)
        .filter(
            TSDocument.id == doc_id,
            TSDocument.deleted_at.is_(None),
            TSDShare.grantee_user_id == actor.id,
            TSDShare.revoked_at.is_(None),
            db.or_(TSDShare.expires_at.is_(None),
                   TSDShare.expires_at > datetime.utcnow()),
        )
        .first()
    )
    if row is None:
        abort(404)
    return row


def _owner_only(doc_id: int) -> TSDocument:
    """Fetch a TSD only if the caller is in the owning tenant.

    Used for share management, delete and other owner-scoped operations.
    """
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


def _share_permission(doc: TSDocument) -> str:
    """Return the acting user's permission on the doc: owner / edit / comment / view."""
    actor = _actor()
    if doc.organization_id == actor.organization_id:
        return "owner"
    share = (
        TSDShare.query
        .filter(
            TSDShare.tsd_id == doc.id,
            TSDShare.grantee_user_id == actor.id,
            TSDShare.revoked_at.is_(None),
        )
        .first()
    )
    if share is None or not share.is_active():
        abort(403)
    return share.permission


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
    # View-only / comment-only grantees cannot mutate content.
    perm = _share_permission(row)
    if perm not in ("owner", "edit"):
        return jsonify({"error": "permission_denied", "permission": perm}), 403

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

        # Snapshot the OLD ciphertext into the versions table before
        # we overwrite the parent row. Append-only; prior versions are
        # never mutated or deleted.
        change_note = (payload.get("change_note") or "").strip() or None
        if change_note and len(change_note) > 500:
            change_note = change_note[:500]
        db.session.add(TSDocumentVersion(
            tsd_id=row.id,
            version=row.version,
            ciphertext=row.ciphertext,
            ciphertext_sha256=row.ciphertext_sha256,
            plaintext_bytes=row.plaintext_bytes,
            created_by_id=row.created_by_id,
            change_note=change_note,
        ))

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


# ============================================================ PDF export


@tsd_api.route("/<int:tsd_id>/export/pdf", methods=["POST"])
@login_required
def export_tsd_pdf(tsd_id: int):
    """Render the decrypted content to PDF, optionally password-protected.

    Body (all optional)::

        {
            "user_password":  "<viewer password>",   # required to open
            "owner_password": "<owner password>"     # permissions control
        }

    ``encrypted_only`` export policy blocks this path.
    """
    row = _owned(tsd_id)
    if row.export_policy != "pdf_allowed":
        record_tsd_operation("export_pdf", "policy_blocked")
        return jsonify({
            "error": "export_policy_denies",
            "policy": row.export_policy,
        }), 403

    payload = request.get_json(silent=True) or {}
    user_password = payload.get("user_password") or None
    owner_password = payload.get("owner_password") or None
    if user_password is not None and not isinstance(user_password, str):
        return jsonify({"error": "user_password_must_be_string"}), 400
    if owner_password is not None and not isinstance(owner_password, str):
        return jsonify({"error": "owner_password_must_be_string"}), 400
    if user_password is not None and (len(user_password) < 4 or len(user_password) > 128):
        return jsonify({"error": "user_password_length", "min": 4, "max": 128}), 400

    try:
        content = decrypt_content_envelope(
            row.ciphertext, organization_id=row.organization_id
        )
    except TSDError as exc:
        record_tsd_operation("export_pdf", "decrypt_failed")
        return jsonify({"error": "decrypt_failed", "message": str(exc)}), 500

    try:
        pdf_bytes = render_html_to_pdf(
            html=content.get("html") or "",
            title=row.title,
            document_id=row.id,
            version=row.version,
            tenant_id=row.organization_id,
            user_password=user_password,
            owner_password=owner_password,
        )
    except PdfExportError as exc:
        record_tsd_operation("export_pdf", "render_failed")
        return jsonify({"error": "render_failed", "message": str(exc)}), 500

    _emit(actor_id=current_user.id, organization_id=row.organization_id,
          action="tsd.export_pdf", resource_id=row.id,
          outcome="encrypted" if user_password else "cleartext")
    db.session.commit()
    record_tsd_operation("export_pdf", "encrypted" if user_password else "cleartext")

    safe_title = "".join(c for c in row.title if c.isalnum() or c in ("-", "_", " ")).strip() or "document"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_title}.pdf"',
            "X-TrustSeal-Document-Id": str(row.id),
            "X-TrustSeal-Document-Version": str(row.version),
            "X-TrustSeal-Pdf-Encrypted": "true" if user_password else "false",
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


# ============================================================ templates


@tsd_api.route("/templates", methods=["GET"])
@login_required
def list_templates():
    _actor()
    return jsonify(tsd_templates.list_templates())


@tsd_api.route("/from-template/<slug>", methods=["POST"])
@login_required
def create_from_template(slug: str):
    """Instantiate a new TSD from a built-in template."""
    actor = _actor()
    tpl = tsd_templates.get_template(slug)
    if tpl is None:
        return jsonify({"error": "template_not_found", "slug": slug}), 404

    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or tpl.title).strip()[:255]
    tags = (payload.get("tags") or tpl.tags or "").strip() or None

    safe_html = sanitize_html(tpl.body_html)
    try:
        plaintext = pack_content(
            html=safe_html,
            description=f"Created from template: {tpl.name}",
            tags=[t.strip() for t in (tags or "").split(",") if t.strip()],
            extras={"template_slug": tpl.slug, "template_category": tpl.category},
        )
        ciphertext = encrypt_content_envelope(
            plaintext, organization_id=actor.organization_id
        )
    except TSDError as exc:
        return jsonify({"error": "encrypt_failed", "message": str(exc)}), 400

    row = TSDocument(
        organization_id=actor.organization_id,
        created_by_id=actor.id,
        title=title,
        description=f"From template: {tpl.name}"[:1000],
        tags=tags,
        export_policy=payload.get("export_policy", "pdf_allowed"),
        status="draft",
        ciphertext=ciphertext,
        ciphertext_sha256=sha256_hex(ciphertext),
        plaintext_bytes=len(plaintext),
    )
    db.session.add(row)
    db.session.flush()
    _emit(actor_id=actor.id, organization_id=actor.organization_id,
          action="tsd.from_template", resource_id=row.id, outcome=tpl.slug)
    db.session.commit()
    record_tsd_operation("from_template")
    record_tsd_plaintext(len(plaintext))
    return jsonify(row.to_dict()), 201


# ============================================================ versions


@tsd_api.route("/<int:tsd_id>/versions", methods=["GET"])
@login_required
def list_versions(tsd_id: int):
    """List prior versions of a TSD. The current version is NOT included
    (fetch that via ``GET /api/tsd/<id>``)."""
    row = _owned(tsd_id)
    versions = (
        TSDocumentVersion.query
        .filter_by(tsd_id=row.id)
        .order_by(TSDocumentVersion.version.desc())
        .all()
    )
    return jsonify([
        {
            "id": v.id,
            "tsd_id": v.tsd_id,
            "version": v.version,
            "ciphertext_sha256": v.ciphertext_sha256,
            "plaintext_bytes": v.plaintext_bytes,
            "created_by_id": v.created_by_id,
            "change_note": v.change_note,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in versions
    ])


@tsd_api.route("/<int:tsd_id>/versions/<int:version>/content", methods=["GET"])
@login_required
def get_version_content(tsd_id: int, version: int):
    """Return the decrypted content of a prior version."""
    row = _owned(tsd_id)
    snap = (
        TSDocumentVersion.query
        .filter_by(tsd_id=row.id, version=version)
        .first()
    )
    if snap is None:
        abort(404, description="version_not_found")

    try:
        content = decrypt_content_envelope(
            snap.ciphertext, organization_id=row.organization_id
        )
    except TSDError as exc:
        return jsonify({"error": "decrypt_failed", "message": str(exc)}), 500

    _emit(actor_id=current_user.id, organization_id=row.organization_id,
          action="tsd.open_version", resource_id=row.id,
          outcome=f"v{version}")
    db.session.commit()
    record_tsd_operation("open_version")

    return jsonify({
        "tsd_id": row.id,
        "version": version,
        "ciphertext_sha256": snap.ciphertext_sha256,
        "plaintext_bytes": snap.plaintext_bytes,
        "change_note": snap.change_note,
        "created_at": snap.created_at.isoformat() if snap.created_at else None,
        "content": content,
    })


@tsd_api.route("/<int:tsd_id>/versions/<int:version>/restore", methods=["POST"])
@login_required
def restore_version(tsd_id: int, version: int):
    """Restore a prior version as the current one.

    The current ciphertext is first snapshotted (so the restore is
    itself reversible), then the chosen prior version becomes the
    active content. Produces a brand-new version number — history is
    linear and append-only.
    """
    row = _owned(tsd_id)
    snap = (
        TSDocumentVersion.query
        .filter_by(tsd_id=row.id, version=version)
        .first()
    )
    if snap is None:
        abort(404, description="version_not_found")

    # Snapshot the current state before overwriting.
    db.session.add(TSDocumentVersion(
        tsd_id=row.id,
        version=row.version,
        ciphertext=row.ciphertext,
        ciphertext_sha256=row.ciphertext_sha256,
        plaintext_bytes=row.plaintext_bytes,
        created_by_id=current_user.id,
        change_note=f"snapshot before restore to v{version}",
    ))

    row.ciphertext = snap.ciphertext
    row.ciphertext_sha256 = snap.ciphertext_sha256
    row.plaintext_bytes = snap.plaintext_bytes
    row.version += 1
    row.updated_at = datetime.utcnow()

    _emit(actor_id=current_user.id, organization_id=row.organization_id,
          action="tsd.restore_version", resource_id=row.id,
          outcome=f"restored_v{version}_as_v{row.version}")
    db.session.commit()
    record_tsd_operation("restore_version")
    return jsonify(row.to_dict())


# ============================================================ shares


@tsd_api.route("/<int:tsd_id>/shares", methods=["GET"])
@login_required
def list_shares(tsd_id: int):
    """List share grants on a TSD. Owner-only."""
    row = _owner_only(tsd_id)
    shares = (
        TSDShare.query
        .filter_by(tsd_id=row.id)
        .order_by(TSDShare.created_at.desc())
        .all()
    )
    # Include the grantee's display name where we have the user record.
    user_ids = [s.grantee_user_id for s in shares if s.grantee_user_id]
    users = {
        u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()
    } if user_ids else {}

    def _with_user(s):
        d = s.to_dict()
        u = users.get(s.grantee_user_id)
        if u:
            d["grantee_name"] = ((u.first_name or "") + " " + (u.last_name or "")).strip() or u.username
            d["grantee_email_resolved"] = u.email
        return d
    return jsonify([_with_user(s) for s in shares])


@tsd_api.route("/<int:tsd_id>/shares", methods=["POST"])
@login_required
def create_share(tsd_id: int):
    """Grant access to another user in the same organization by email."""
    row = _owner_only(tsd_id)
    actor = _actor()

    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    permission = (payload.get("permission") or "view").lower()
    expires_in_days = payload.get("expires_in_days")

    if not email:
        return jsonify({"error": "email_required"}), 400
    if permission not in TSD_SHARE_PERMISSIONS:
        return jsonify({"error": "invalid_permission",
                        "allowed": list(TSD_SHARE_PERMISSIONS)}), 400

    # Resolve grantee user (same tenant only).
    grantee = (
        User.query
        .filter(User.email == email,
                User.organization_id == row.organization_id,
                User.is_active.is_(True))
        .first()
    )

    if grantee is None:
        return jsonify({
            "error": "grantee_not_in_tenant",
            "message": f"No active user with email {email!r} in this workspace. "
                       f"External sharing is not enabled in this phase.",
        }), 404
    if grantee.id == actor.id:
        return jsonify({"error": "cannot_share_with_self"}), 400

    expires_at = None
    if expires_in_days is not None:
        try:
            days = int(expires_in_days)
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_expires_in_days"}), 400
        if days < 1 or days > 365:
            return jsonify({"error": "expires_in_days_out_of_range",
                            "min": 1, "max": 365}), 400
        expires_at = datetime.utcnow() + timedelta(days=days)

    # Upsert: if a share already exists for this grantee, reactivate it.
    existing = (
        TSDShare.query
        .filter_by(tsd_id=row.id, grantee_user_id=grantee.id)
        .first()
    )
    if existing is not None:
        existing.permission = permission
        existing.expires_at = expires_at
        existing.revoked_at = None
        existing.created_by_id = actor.id
        share = existing
    else:
        share = TSDShare(
            tsd_id=row.id,
            organization_id=row.organization_id,
            grantee_user_id=grantee.id,
            grantee_email=grantee.email,
            permission=permission,
            created_by_id=actor.id,
            expires_at=expires_at,
        )
        db.session.add(share)

    _emit(actor_id=actor.id, organization_id=row.organization_id,
          action="tsd.share", resource_id=row.id,
          outcome=f"{permission}:user_{grantee.id}")
    db.session.commit()
    record_tsd_operation("share")

    d = share.to_dict()
    d["grantee_name"] = ((grantee.first_name or "") + " " + (grantee.last_name or "")).strip() or grantee.username
    d["grantee_email_resolved"] = grantee.email
    return jsonify(d), 201


@tsd_api.route("/<int:tsd_id>/shares/<int:share_id>", methods=["DELETE"])
@login_required
def revoke_share(tsd_id: int, share_id: int):
    """Revoke a share grant. Owner-only. Row is kept for audit — only
    ``revoked_at`` is set."""
    row = _owner_only(tsd_id)
    actor = _actor()
    share = (
        TSDShare.query
        .filter_by(id=share_id, tsd_id=row.id)
        .first()
    )
    if share is None:
        abort(404)
    if share.revoked_at is not None:
        return jsonify({"error": "already_revoked"}), 409
    share.revoked_at = datetime.utcnow()
    _emit(actor_id=actor.id, organization_id=row.organization_id,
          action="tsd.share_revoke", resource_id=row.id,
          outcome=f"share_{share.id}")
    db.session.commit()
    record_tsd_operation("share_revoke")
    return "", 204


# ============================================================ comments


@tsd_api.route("/<int:tsd_id>/comments", methods=["GET"])
@login_required
def list_comments(tsd_id: int):
    """List all comments on a TSD, including resolved ones for context."""
    row = _owned(tsd_id)
    comments = (
        TSDComment.query
        .filter_by(tsd_id=row.id)
        .order_by(TSDComment.created_at.asc())
        .all()
    )
    authors = {}
    author_ids = {c.author_id for c in comments}
    if author_ids:
        authors = {u.id: u for u in User.query.filter(User.id.in_(author_ids)).all()}

    def _with_author(c):
        d = c.to_dict()
        u = authors.get(c.author_id)
        if u:
            d["author_name"] = ((u.first_name or "") + " " + (u.last_name or "")).strip() or u.username
        return d
    return jsonify([_with_author(c) for c in comments])


@tsd_api.route("/<int:tsd_id>/comments", methods=["POST"])
@login_required
def create_comment(tsd_id: int):
    """Create a new comment thread or a reply."""
    row = _owned(tsd_id)
    perm = _share_permission(row)
    if perm not in ("owner", "edit", "comment"):
        return jsonify({"error": "permission_denied"}), 403

    payload = request.get_json(silent=True) or {}
    body = (payload.get("body") or "").strip()
    if not body:
        return jsonify({"error": "body_required"}), 400
    if len(body) > 4000:
        return jsonify({"error": "body_too_long", "max": 4000}), 400

    parent_id = payload.get("parent_comment_id")
    if parent_id is not None:
        parent = TSDComment.query.filter_by(id=parent_id, tsd_id=row.id).first()
        if parent is None:
            return jsonify({"error": "parent_comment_not_found"}), 404

    comment = TSDComment(
        tsd_id=row.id,
        parent_comment_id=parent_id,
        author_id=current_user.id,
        body=sanitize_html(body) if '<' in body else body,
        anchor_id=(payload.get("anchor_id") or None),
        anchor_text=(payload.get("anchor_text") or "")[:500] or None,
    )
    db.session.add(comment)
    db.session.flush()
    _emit(actor_id=current_user.id, organization_id=row.organization_id,
          action="tsd.comment", resource_id=row.id,
          outcome=f"comment_{comment.id}")
    db.session.commit()
    record_tsd_operation("comment")
    return jsonify(comment.to_dict()), 201


@tsd_api.route("/<int:tsd_id>/comments/<int:comment_id>/resolve", methods=["POST"])
@login_required
def resolve_comment(tsd_id: int, comment_id: int):
    """Resolve a comment thread (idempotent)."""
    row = _owned(tsd_id)
    perm = _share_permission(row)
    if perm not in ("owner", "edit", "comment"):
        return jsonify({"error": "permission_denied"}), 403

    c = TSDComment.query.filter_by(id=comment_id, tsd_id=row.id).first()
    if c is None:
        abort(404)
    if c.resolved_at is None:
        c.resolved_at = datetime.utcnow()
        c.resolved_by_id = current_user.id
        _emit(actor_id=current_user.id, organization_id=row.organization_id,
              action="tsd.comment_resolve", resource_id=row.id,
              outcome=f"comment_{c.id}")
        db.session.commit()
        record_tsd_operation("comment_resolve")
    return jsonify(c.to_dict())


@tsd_api.route("/<int:tsd_id>/comments/<int:comment_id>/reopen", methods=["POST"])
@login_required
def reopen_comment(tsd_id: int, comment_id: int):
    row = _owned(tsd_id)
    perm = _share_permission(row)
    if perm not in ("owner", "edit", "comment"):
        return jsonify({"error": "permission_denied"}), 403
    c = TSDComment.query.filter_by(id=comment_id, tsd_id=row.id).first()
    if c is None:
        abort(404)
    c.resolved_at = None
    c.resolved_by_id = None
    db.session.commit()
    return jsonify(c.to_dict())


@tsd_api.route("/<int:tsd_id>/comments/<int:comment_id>", methods=["DELETE"])
@login_required
def delete_comment(tsd_id: int, comment_id: int):
    """Delete a comment. Only the author or the document owner may delete."""
    row = _owned(tsd_id)
    c = TSDComment.query.filter_by(id=comment_id, tsd_id=row.id).first()
    if c is None:
        abort(404)
    is_owner = (row.organization_id == current_user.organization_id)
    if c.author_id != current_user.id and not is_owner:
        return jsonify({"error": "permission_denied"}), 403
    db.session.delete(c)
    db.session.commit()
    return "", 204


# ============================================================ external shares


@tsd_api.route("/<int:tsd_id>/external-shares", methods=["GET"])
@login_required
def list_external_shares(tsd_id: int):
    row = _owner_only(tsd_id)
    items = (
        TSDExternalShare.query
        .filter_by(tsd_id=row.id)
        .order_by(TSDExternalShare.created_at.desc())
        .all()
    )
    return jsonify([s.to_dict() for s in items])


@tsd_api.route("/<int:tsd_id>/external-shares", methods=["POST"])
@login_required
def create_external_share(tsd_id: int):
    """Create a magic-link grant for a non-tenant email."""
    row = _owner_only(tsd_id)
    actor = _actor()
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    permission = (payload.get("permission") or "view").lower()
    expires_in_days = payload.get("expires_in_days") or 14

    if not email:
        return jsonify({"error": "email_required"}), 400
    if permission not in EXTERNAL_SHARE_PERMISSIONS:
        return jsonify({"error": "invalid_permission",
                        "allowed": list(EXTERNAL_SHARE_PERMISSIONS)}), 400
    try:
        days = int(expires_in_days)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_expires_in_days"}), 400
    if days < 1 or days > 90:
        return jsonify({"error": "expires_in_days_out_of_range",
                        "min": 1, "max": 90}), 400

    token = new_token()
    share = TSDExternalShare(
        tsd_id=row.id,
        organization_id=row.organization_id,
        recipient_email=email,
        permission=permission,
        token_hash=hash_token(token),
        expires_at=datetime.utcnow() + timedelta(days=days),
        created_by_id=actor.id,
    )
    db.session.add(share)
    db.session.flush()

    # Dispatch the magic link via the configured mail transport.
    from flask import url_for
    from app.services.email import send, EmailMessage
    link = url_for("tsd_external_views.landing",
                   share_id=share.id, token=token, _external=True)
    try:
        send(EmailMessage(
            to=email,
            subject=f"{row.title} — shared with you on TRUSTSEAL",
            body_text=(
                f"A TRUSTSEAL document has been shared with you:\n\n"
                f"  {row.title}\n\n"
                f"Open the document (link expires in {days} day{'s' if days != 1 else ''}):\n"
                f"  {link}\n\n"
                f"This grant is view-only unless the sender chose 'comment'.\n"
                f"If you believe you received this in error, ignore this email."
            ),
        ))
    except Exception as exc:
        # Still commit the grant — the admin can re-share if the email failed.
        current_app.logger.warning("tsd external share email failed: %s", exc)

    _emit(actor_id=actor.id, organization_id=row.organization_id,
          action="tsd.external_share", resource_id=row.id,
          outcome=f"{permission}:{email}")
    db.session.commit()
    record_tsd_operation("external_share")

    # Return the RAW token exactly once; the DB only stores its hash.
    result = share.to_dict()
    result["token"] = token
    result["link"] = link
    return jsonify(result), 201


@tsd_api.route("/<int:tsd_id>/external-shares/<int:share_id>", methods=["DELETE"])
@login_required
def revoke_external_share(tsd_id: int, share_id: int):
    row = _owner_only(tsd_id)
    s = TSDExternalShare.query.filter_by(id=share_id, tsd_id=row.id).first()
    if s is None:
        abort(404)
    if s.revoked_at is not None:
        return jsonify({"error": "already_revoked"}), 409
    s.revoked_at = datetime.utcnow()
    _emit(actor_id=current_user.id, organization_id=row.organization_id,
          action="tsd.external_share_revoke", resource_id=row.id,
          outcome=f"external_share_{s.id}")
    db.session.commit()
    record_tsd_operation("external_share_revoke")
    return "", 204


# ============================================================ approvals


@tsd_api.route("/<int:tsd_id>/approvals", methods=["GET"])
@login_required
def list_approvals(tsd_id: int):
    row = _owned(tsd_id)
    items = (
        TSDApproval.query
        .filter_by(tsd_id=row.id)
        .order_by(TSDApproval.order_index.asc(), TSDApproval.id.asc())
        .all()
    )
    approver_ids = {a.approver_id for a in items}
    users = {u.id: u for u in User.query.filter(User.id.in_(approver_ids)).all()} if approver_ids else {}

    def _with_user(a):
        d = a.to_dict()
        u = users.get(a.approver_id)
        if u:
            d["approver_name"] = ((u.first_name or "") + " " + (u.last_name or "")).strip() or u.username
            d["approver_email"] = u.email
        return d

    # Derive the overall workflow state (see model docstring).
    statuses = [a.status for a in items]
    if not items:
        wf_state = "none"
    elif any(s == "rejected" for s in statuses):
        wf_state = "rejected"
    elif any(s == "changes_requested" for s in statuses):
        wf_state = "changes_requested"
    elif all(s == "approved" for s in statuses):
        wf_state = "approved"
    elif all(s == "pending" for s in statuses):
        wf_state = "awaiting_first"
    else:
        wf_state = "in_progress"

    return jsonify({
        "workflow_state": wf_state,
        "approvals": [_with_user(a) for a in items],
    })


@tsd_api.route("/<int:tsd_id>/approvals", methods=["POST"])
@login_required
def request_approvals(tsd_id: int):
    """Owner adds one or more approvers at a given step.

    Body: ``{"approver_emails": ["a@x", "b@x"], "order_index": 0}``
    Approvers with the same ``order_index`` act in parallel; higher
    indices run after lower ones complete.
    """
    row = _owner_only(tsd_id)
    actor = _actor()
    payload = request.get_json(silent=True) or {}
    emails = payload.get("approver_emails") or []
    try:
        order_index = int(payload.get("order_index", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_order_index"}), 400
    if not isinstance(emails, list) or not emails:
        return jsonify({"error": "approver_emails_required"}), 400

    created = []
    for raw in emails:
        email = (raw or "").strip().lower()
        if not email:
            continue
        user = (
            User.query
            .filter(User.email == email,
                    User.organization_id == row.organization_id,
                    User.is_active.is_(True))
            .first()
        )
        if user is None:
            return jsonify({"error": "approver_not_in_tenant", "email": email}), 404
        # Skip if already an approver (uq constraint).
        if TSDApproval.query.filter_by(tsd_id=row.id, approver_id=user.id).first():
            continue
        a = TSDApproval(
            tsd_id=row.id,
            organization_id=row.organization_id,
            approver_id=user.id,
            order_index=order_index,
            created_by_id=actor.id,
        )
        db.session.add(a)
        db.session.flush()
        created.append(a.id)
        # Mail the approver.
        try:
            from app.services.email import send, EmailMessage
            from flask import url_for
            link = url_for("tsd_views.edit", tsd_id=row.id, _external=True)
            send(EmailMessage(
                to=user.email,
                subject=f"Approval requested: {row.title}",
                body_text=(
                    f"{actor.email} has requested your approval on a TRUSTSEAL document:\n\n"
                    f"  {row.title}\n\n"
                    f"Review and decide:\n  {link}"
                ),
            ))
        except Exception as exc:
            current_app.logger.warning("approval email failed: %s", exc)

    _emit(actor_id=actor.id, organization_id=row.organization_id,
          action="tsd.approvals_requested", resource_id=row.id,
          outcome=f"created_{len(created)}")
    db.session.commit()
    record_tsd_operation("approvals_requested")
    return jsonify({"created": created}), 201


@tsd_api.route("/<int:tsd_id>/approvals/<int:approval_id>/decide", methods=["POST"])
@login_required
def decide_approval(tsd_id: int, approval_id: int):
    """Approver records their decision.

    Body: ``{"decision": "approved"|"rejected"|"changes_requested",
              "note": "optional free-text"}``
    """
    row = _owned(tsd_id)
    a = TSDApproval.query.filter_by(id=approval_id, tsd_id=row.id).first()
    if a is None:
        abort(404)
    if a.approver_id != current_user.id:
        return jsonify({"error": "not_your_approval"}), 403
    if a.status != "pending":
        return jsonify({"error": "already_decided", "status": a.status}), 409

    # Sequential enforcement: all approvals at lower order_index must be
    # completed (any non-pending status) before this step can decide.
    blocking = (
        TSDApproval.query
        .filter(TSDApproval.tsd_id == row.id,
                TSDApproval.order_index < a.order_index,
                TSDApproval.status == "pending")
        .first()
    )
    if blocking is not None:
        return jsonify({"error": "earlier_step_pending",
                        "blocking_step": blocking.order_index}), 409

    payload = request.get_json(silent=True) or {}
    decision = payload.get("decision")
    if decision not in ("approved", "rejected", "changes_requested"):
        return jsonify({"error": "invalid_decision",
                        "allowed": ["approved", "rejected", "changes_requested"]}), 400
    note = (payload.get("note") or "").strip() or None
    if note and len(note) > 1000:
        note = note[:1000]

    a.status = decision
    a.note = note
    a.decided_at = datetime.utcnow()
    _emit(actor_id=current_user.id, organization_id=row.organization_id,
          action="tsd.approval_decide", resource_id=row.id,
          outcome=f"{decision}_approval_{a.id}")
    db.session.commit()
    record_tsd_operation("approval_decide")
    return jsonify(a.to_dict())


# ============================================================ presence


@tsd_api.route("/<int:tsd_id>/presence", methods=["POST"])
@login_required
def ping_presence(tsd_id: int):
    """Mark the caller as currently viewing this TSD.

    Call every 15 s from the editor; a viewer is considered active while
    their last ping is within the last 45 s.
    """
    row = _owned(tsd_id)
    actor = _actor()
    p = db.session.get(TSDPresence, (row.id, actor.id))
    if p is None:
        p = TSDPresence(tsd_id=row.id, user_id=actor.id)
        db.session.add(p)
    else:
        p.last_ping_at = datetime.utcnow()
    db.session.commit()
    return "", 204


@tsd_api.route("/<int:tsd_id>/presence", methods=["GET"])
@login_required
def list_presence(tsd_id: int):
    """List users active in the last 45 seconds."""
    row = _owned(tsd_id)
    threshold = datetime.utcnow() - timedelta(seconds=45)
    rows = (
        db.session.query(TSDPresence, User)
        .join(User, User.id == TSDPresence.user_id)
        .filter(TSDPresence.tsd_id == row.id,
                TSDPresence.last_ping_at >= threshold)
        .order_by(TSDPresence.last_ping_at.desc())
        .all()
    )
    return jsonify([
        {
            "user_id": u.id,
            "name": ((u.first_name or "") + " " + (u.last_name or "")).strip() or u.username,
            "email": u.email,
            "initials": ((u.first_name or u.username or "?")[:1] + (u.last_name or "")[:1]).upper(),
            "last_ping_at": p.last_ping_at.isoformat() if p.last_ping_at else None,
        }
        for (p, u) in rows
    ])


# ============================================================ delete


@tsd_api.route("/<int:tsd_id>", methods=["DELETE"])
@login_required
def delete_tsd(tsd_id: int):
    row = _owner_only(tsd_id)

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
