"""REST APIs for Tenant Media Library and Official Letterheads."""
from __future__ import annotations

import base64
import hashlib
import io
from datetime import datetime

from flask import Blueprint, abort, jsonify, request, send_file
from flask_login import current_user, login_required
from PIL import Image

from app.extensions import db
from app.models.media_asset import MEDIA_CATEGORIES, MediaAsset
from app.models.tsd_letterhead import (
    LETTERHEAD_PRESETS,
    TSDLetterhead,
    render_letterhead_parts,
)


media_library_api = Blueprint("media_library_api", __name__, url_prefix="/api/media-library")
letterheads_api = Blueprint("letterheads_api", __name__, url_prefix="/api/letterheads")

_ALLOWED_MIMES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/svg+xml",
}
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


def _actor():
    if not current_user.is_authenticated:
        abort(401)
    if current_user.organization_id is None:
        abort(403, description="organization_required")
    return current_user


def _ensure_tables() -> None:
    """Safely ensure new tables exist on first access without requiring manual migration."""
    try:
        MediaAsset.__table__.create(bind=db.engine, checkfirst=True)
        TSDLetterhead.__table__.create(bind=db.engine, checkfirst=True)
    except Exception:
        pass


def _probe_dimensions(raw: bytes, mime: str) -> tuple[int | None, int | None]:
    if mime == "image/svg+xml":
        return None, None
    try:
        with Image.open(io.BytesIO(raw)) as im:
            return int(im.width), int(im.height)
    except Exception:
        return None, None


# ============================================================ Media Library API


@media_library_api.route("/", methods=["GET"])
@login_required
def list_media():
    actor = _actor()
    _ensure_tables()
    q = MediaAsset.query.filter(
        MediaAsset.organization_id == actor.organization_id,
        MediaAsset.deleted_at.is_(None),
    )
    cat = (request.args.get("category") or "").strip().lower()
    if cat and cat != "all":
        q = q.filter(MediaAsset.category == cat)
    search = (request.args.get("q") or "").strip().lower()
    rows = q.order_by(MediaAsset.created_at.desc()).limit(300).all()
    if search:
        rows = [r for r in rows if search in (r.name or "").lower() or search in (r.category or "").lower()]
    return jsonify({
        "count": len(rows),
        "assets": [r.to_dict(include_data=True) for r in rows],
    })


def _autotrim_raster_logo(raw_bytes: bytes, mime: str) -> tuple[bytes, str]:
    """Strip transparent, white, and near-white top/bottom/left/right margins from a raster logo."""
    if not raw_bytes or mime == "image/svg+xml":
        return raw_bytes, mime
    try:
        im = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
        w, h = im.size
        if w < 2 or h < 2:
            return raw_bytes, mime
        px = im.load()

        # Sample corners/edges to detect uniform opaque light/white background
        edge_pts = [
            (0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
            (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2),
        ]
        opaque_edges = [px[x, y][:3] for (x, y) in edge_pts if px[x, y][3] > 200]
        bg = None
        if len(opaque_edges) >= 4:
            ar = sum(c[0] for c in opaque_edges) // len(opaque_edges)
            ag = sum(c[1] for c in opaque_edges) // len(opaque_edges)
            ab = sum(c[2] for c in opaque_edges) // len(opaque_edges)
            close = sum(
                1 for (r, g, b) in opaque_edges
                if (r - ar) ** 2 + (g - ag) ** 2 + (b - ab) ** 2 < 44 * 44
            )
            if close >= int(len(opaque_edges) * 0.65):
                bg = (ar, ag, ab)

        # Make background pixels transparent (soft feathering)
        if bg is not None:
            tol = 36 if (bg[0] + bg[1] + bg[2] > 690) else 24
            tol2 = tol * tol
            f2 = (tol + 14) ** 2
            br, bg_g, bb = bg
            for y in range(h):
                for x in range(w):
                    r, g, b, a = px[x, y]
                    if a < 10:
                        continue
                    d2 = (r - br) ** 2 + (g - bg_g) ** 2 + (b - bb) ** 2
                    if d2 <= tol2:
                        px[x, y] = (r, g, b, 0)
                    elif d2 < f2:
                        k = (d2 - tol2) / float(f2 - tol2)
                        px[x, y] = (r, g, b, int(a * k))

        # Tight bounding box over visible non-near-white pixels
        min_x, min_y, max_x, max_y = w, h, -1, -1
        for y in range(h):
            for x in range(w):
                r, g, b, a = px[x, y]
                if a <= 20:
                    continue
                if r > 236 and g > 236 and b > 236:
                    continue
                if x < min_x:
                    min_x = x
                if x > max_x:
                    max_x = x
                if y < min_y:
                    min_y = y
                if y > max_y:
                    max_y = y

        if max_x < min_x or max_y < min_y:
            return raw_bytes, mime

        cropped = im.crop((min_x, min_y, max_x + 1, max_y + 1))
        out = io.BytesIO()
        cropped.save(out, format="PNG", optimize=True)
        return out.getvalue(), "image/png"
    except Exception:
        return raw_bytes, mime


@media_library_api.route("/", methods=["POST"])
@login_required
def upload_media():
    actor = _actor()
    _ensure_tables()

    name = ""
    category = "logo"
    mime = "image/png"
    raw_bytes: bytes | None = None
    data_uri = ""

    if "file" in request.files and request.files["file"].filename:
        f = request.files["file"]
        raw_bytes = f.read(_MAX_BYTES + 1)
        if len(raw_bytes) > _MAX_BYTES:
            return jsonify({"error": "file_too_large"}), 400
        mime = (f.mimetype or "").lower().strip()
        if not mime or mime == "application/octet-stream":
            import mimetypes as _mt
            guessed, _ = _mt.guess_type(f.filename or "")
            mime = (guessed or "image/png").lower()
        if mime == "image/jpg":
            mime = "image/jpeg"
        if mime not in _ALLOWED_MIMES:
            return jsonify({"error": "unsupported_image_type", "mime": mime}), 400
        name = (request.form.get("name") or f.filename or "Untitled asset").strip()[:140]
        category = (request.form.get("category") or "logo").strip().lower()
        data_uri = f"data:{mime};base64," + base64.b64encode(raw_bytes).decode("ascii")
    else:
        payload = request.get_json(silent=True) or {}
        name = (payload.get("name") or "Untitled asset").strip()[:140]
        category = (payload.get("category") or "logo").strip().lower()
        data_uri = (payload.get("data_uri") or "").strip()
        if not data_uri.startswith("data:image/") or "," not in data_uri:
            return jsonify({"error": "invalid_data_uri"}), 400
        head, b64 = data_uri.split(",", 1)
        mime = head[5:].split(";")[0].lower()
        if mime == "image/jpg":
            mime = "image/jpeg"
        if mime not in _ALLOWED_MIMES:
            return jsonify({"error": "unsupported_image_type"}), 400
        try:
            raw_bytes = base64.b64decode(b64)
        except Exception:
            return jsonify({"error": "invalid_base64"}), 400
        if len(raw_bytes) > _MAX_BYTES:
            return jsonify({"error": "file_too_large"}), 400

    if category not in MEDIA_CATEGORIES:
        category = "general"

    if category == "logo" and raw_bytes and mime != "image/svg+xml":
        raw_bytes, mime = _autotrim_raster_logo(raw_bytes, mime)
        data_uri = f"data:{mime};base64," + base64.b64encode(raw_bytes).decode("ascii")

    w, h = _probe_dimensions(raw_bytes or b"", mime)
    digest = hashlib.sha256(raw_bytes or b"").hexdigest()

    row = MediaAsset(
        organization_id=actor.organization_id,
        uploaded_by_id=actor.id,
        name=name or "Untitled asset",
        category=category,
        mime_type=mime,
        data_uri=data_uri,
        width=w,
        height=h,
        size_bytes=len(raw_bytes or b""),
        sha256=digest,
    )
    db.session.add(row)
    db.session.commit()
    return jsonify(row.to_dict(include_data=True)), 201


@media_library_api.route("/<int:asset_id>", methods=["PUT"])
@login_required
def update_media(asset_id: int):
    actor = _actor()
    _ensure_tables()
    row = db.session.get(MediaAsset, asset_id)
    if row is None or row.organization_id != actor.organization_id or row.deleted_at is not None:
        abort(404)
    payload = request.get_json(silent=True) or {}
    if "name" in payload:
        name = (payload.get("name") or "").strip()[:140]
        if name:
            row.name = name
    if "category" in payload:
        cat = (payload.get("category") or "").strip().lower()
        if cat in MEDIA_CATEGORIES:
            row.category = cat
    db.session.commit()
    return jsonify(row.to_dict(include_data=True))


@media_library_api.route("/<int:asset_id>/download", methods=["GET"])
@login_required
def download_media(asset_id: int):
    actor = _actor()
    _ensure_tables()
    row = db.session.get(MediaAsset, asset_id)
    if row is None or row.organization_id != actor.organization_id or row.deleted_at is not None:
        abort(404)
    if "," not in (row.data_uri or ""):
        abort(404)
    raw = base64.b64decode(row.data_uri.split(",", 1)[1])
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/svg+xml": "svg"}.get(row.mime_type, "png")
    return send_file(
        io.BytesIO(raw),
        mimetype=row.mime_type or "image/png",
        as_attachment=True,
        download_name=f"{row.name}.{ext}",
    )


@media_library_api.route("/<int:asset_id>", methods=["DELETE"])
@login_required
def delete_media(asset_id: int):
    actor = _actor()
    _ensure_tables()
    row = db.session.get(MediaAsset, asset_id)
    if row is None or row.organization_id != actor.organization_id or row.deleted_at is not None:
        abort(404)
    row.deleted_at = datetime.utcnow()
    db.session.commit()
    return "", 204


# ============================================================ Letterheads API


@letterheads_api.route("/", methods=["GET"])
@login_required
def list_letterheads():
    actor = _actor()
    _ensure_tables()
    rows = (
        TSDLetterhead.query
        .filter(
            TSDLetterhead.organization_id == actor.organization_id,
            TSDLetterhead.deleted_at.is_(None),
        )
        .order_by(TSDLetterhead.is_default.desc(), TSDLetterhead.updated_at.desc())
        .all()
    )
    return jsonify({
        "count": len(rows),
        "letterheads": [r.to_dict() for r in rows],
    })


@letterheads_api.route("/", methods=["POST"])
@login_required
def create_letterhead():
    actor = _actor()
    _ensure_tables()
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()[:140]
    if not name:
        return jsonify({"error": "name_required"}), 400
    description = (payload.get("description") or "").strip()[:300] or None
    layout = payload.get("layout") if isinstance(payload.get("layout"), dict) else {}
    is_default = bool(payload.get("is_default", False))

    header_html, footer_html = render_letterhead_parts(layout)
    if is_default:
        TSDLetterhead.query.filter(
            TSDLetterhead.organization_id == actor.organization_id,
            TSDLetterhead.deleted_at.is_(None),
        ).update({"is_default": False})

    row = TSDLetterhead(
        organization_id=actor.organization_id,
        created_by_id=actor.id,
        name=name,
        description=description,
        is_default=is_default,
        status="active",
        layout=layout,
        header_html=header_html,
        footer_html=footer_html,
    )
    db.session.add(row)
    db.session.commit()
    return jsonify(row.to_dict()), 201


@letterheads_api.route("/<int:lh_id>", methods=["PUT"])
@login_required
def update_letterhead(lh_id: int):
    actor = _actor()
    _ensure_tables()
    row = db.session.get(TSDLetterhead, lh_id)
    if row is None or row.organization_id != actor.organization_id or row.deleted_at is not None:
        abort(404)
    payload = request.get_json(silent=True) or {}
    if "name" in payload:
        name = (payload.get("name") or "").strip()[:140]
        if not name:
            return jsonify({"error": "name_required"}), 400
        row.name = name
    if "description" in payload:
        row.description = (payload.get("description") or "").strip()[:300] or None
    if isinstance(payload.get("layout"), dict):
        row.layout = payload["layout"]
        row.header_html, row.footer_html = render_letterhead_parts(row.layout)
    if payload.get("is_default") is True:
        TSDLetterhead.query.filter(
            TSDLetterhead.organization_id == actor.organization_id,
            TSDLetterhead.deleted_at.is_(None),
            TSDLetterhead.id != row.id,
        ).update({"is_default": False})
        row.is_default = True
    elif payload.get("is_default") is False:
        row.is_default = False
    db.session.commit()
    return jsonify(row.to_dict())


@letterheads_api.route("/<int:lh_id>/set-default", methods=["POST"])
@login_required
def set_default_letterhead(lh_id: int):
    actor = _actor()
    _ensure_tables()
    row = db.session.get(TSDLetterhead, lh_id)
    if row is None or row.organization_id != actor.organization_id or row.deleted_at is not None:
        abort(404)
    TSDLetterhead.query.filter(
        TSDLetterhead.organization_id == actor.organization_id,
        TSDLetterhead.deleted_at.is_(None),
    ).update({"is_default": False})
    row.is_default = True
    db.session.commit()
    return jsonify(row.to_dict())


@letterheads_api.route("/presets", methods=["GET"])
@login_required
def list_letterhead_presets():
    _actor()
    return jsonify({"presets": LETTERHEAD_PRESETS})


@letterheads_api.route("/<int:lh_id>", methods=["GET"])
@login_required
def get_letterhead(lh_id: int):
    actor = _actor()
    _ensure_tables()
    row = db.session.get(TSDLetterhead, lh_id)
    if row is None or row.organization_id != actor.organization_id or row.deleted_at is not None:
        abort(404)
    return jsonify(row.to_dict())


@letterheads_api.route("/<int:lh_id>/duplicate", methods=["POST"])
@login_required
def duplicate_letterhead(lh_id: int):
    actor = _actor()
    _ensure_tables()
    src = db.session.get(TSDLetterhead, lh_id)
    if src is None or src.organization_id != actor.organization_id or src.deleted_at is not None:
        abort(404)
    copy_layout = dict(src.layout or {})
    hdr, ftr = render_letterhead_parts(copy_layout)
    row = TSDLetterhead(
        organization_id=actor.organization_id,
        created_by_id=actor.id,
        name=f"{src.name} (Copy)"[:140],
        description=src.description,
        is_default=False,
        status="active",
        layout=copy_layout,
        header_html=hdr,
        footer_html=ftr,
    )
    db.session.add(row)
    db.session.commit()
    return jsonify(row.to_dict()), 201


def _hex_to_rl_rgb(hex_color: str, fallback: tuple[float, float, float] = (0.118, 0.294, 0.62)) -> tuple[float, float, float]:
    h = (hex_color or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return fallback
    try:
        return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0)
    except ValueError:
        return fallback


def render_letterhead_pdf_bytes(row: TSDLetterhead) -> bytes:
    """Render a full-fidelity vector PDF for a saved letterhead."""
    from app.services.letterhead_pdf import render_letterhead_pdf_from_config
    return render_letterhead_pdf_from_config(row.layout or {}, title=row.name or "Official Letterhead")


@letterheads_api.route("/preview.pdf", methods=["POST"])
@login_required
def preview_live_letterhead_pdf():
    """Render a live vector PDF directly from the designer's current layout JSON."""
    _actor()
    from app.services.letterhead_pdf import render_letterhead_pdf_from_config
    payload = request.get_json(silent=True) or {}
    layout = payload.get("layout") if isinstance(payload.get("layout"), dict) else payload
    name = (payload.get("name") or "Official Letterhead").strip()[:120] or "Official Letterhead"
    pdf_bytes = render_letterhead_pdf_from_config(layout or {}, title=name)
    safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_", " ") else "_" for ch in name).strip() or "letterhead"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{safe_name}.pdf",
    )


@letterheads_api.route("/<int:lh_id>/preview.pdf", methods=["GET"])
@login_required
def preview_letterhead_pdf(lh_id: int):
    actor = _actor()
    _ensure_tables()
    row = db.session.get(TSDLetterhead, lh_id)
    if row is None or row.organization_id != actor.organization_id or row.deleted_at is not None:
        abort(404)
    pdf_bytes = render_letterhead_pdf_bytes(row)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{row.name}-letterhead.pdf",
    )


@letterheads_api.route("/<int:lh_id>/create-document", methods=["POST"])
@login_required
def create_document_from_letterhead(lh_id: int):
    """Create a new encrypted TrustSeal Document pre-wrapped with this official letterhead."""
    from app.models.tsd_document import TSDocument
    from app.services.signature_attestations import (
        SignatureAttestationError,
        validate_document_signatures,
    )
    from app.services.tsd_format import (
        encrypt_content_envelope,
        pack_content,
        sanitize_html,
        sha256_hex,
    )

    actor = _actor()
    _ensure_tables()
    lh = db.session.get(TSDLetterhead, lh_id)
    if lh is None or lh.organization_id != actor.organization_id or lh.deleted_at is not None:
        abort(404)

    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or f"Official Document · {lh.name}").strip()[:240]
    custom_body = (payload.get("body_html") or "").strip()
    inner_body = custom_body if custom_body else '<p><strong>RE: </strong></p><p><br></p>'
    body_html = sanitize_html(
        (lh.header_html or "")
        + '<div class="tsd-letterhead-body" style="min-height:260pt;padding:8pt 0;">'
        + inner_body
        + '</div>'
        + (lh.footer_html or "")
    )
    try:
        validate_document_signatures(
            html=body_html,
            organization_id=actor.organization_id,
            document_id=None,
        )
    except SignatureAttestationError as exc:
        return jsonify({"error": "invalid_signature", "message": str(exc)}), 400
    plaintext = pack_content(
        html=body_html,
        description=f"Drafted on letterhead: {lh.name}",
        tags=["letterhead"],
        extras={"letterhead_id": lh.id, "letterhead_name": lh.name},
    )
    ciphertext = encrypt_content_envelope(plaintext, organization_id=actor.organization_id)
    doc = TSDocument(
        organization_id=actor.organization_id,
        created_by_id=actor.id,
        title=title,
        description=f"Official letterhead: {lh.name}",
        tags="letterhead",
        export_policy="pdf_allowed",
        status="draft",
        ciphertext=ciphertext,
        ciphertext_sha256=sha256_hex(ciphertext),
        plaintext_bytes=len(plaintext),
    )
    db.session.add(doc)
    db.session.commit()
    return jsonify({
        "id": doc.id,
        "title": doc.title,
        "letterhead_id": lh.id,
        "editor_url": f"/documents/library/{doc.id}",
    }), 201


@letterheads_api.route("/<int:lh_id>", methods=["DELETE"])
@login_required
def delete_letterhead(lh_id: int):
    actor = _actor()
    _ensure_tables()
    row = db.session.get(TSDLetterhead, lh_id)
    if row is None or row.organization_id != actor.organization_id or row.deleted_at is not None:
        abort(404)
    row.deleted_at = datetime.utcnow()
    row.is_default = False
    db.session.commit()
    return "", 204
