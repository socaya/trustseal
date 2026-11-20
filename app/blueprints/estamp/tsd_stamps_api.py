"""TSD Stamp Studio API — tenant-owned SVG stamp designs.

Admin-free: anyone in the tenant can design + register a stamp for
inline insertion into TSDs. The heavier
``managed_stamps``/``stamp_design_versions`` workflow (custody,
approval, PDF appearance) stays untouched for cryptographically-
attested PDF sealing.
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime

from flask import Blueprint, abort, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import func

from app.extensions import db
from app.models.device_profile import DeviceProfile
from app.models.event_delivery import SecurityEvent
from app.models.tsd_document import TSDocument
from app.models.tsd_stamp import TSD_STAMP_KINDS, TSDStamp
from app.models.tsd_stamp_insertion import TSDStampInsertion
from app.models.tsd_stamp_revision import TSDStampRevision
from app.models.user import User
from app.services import tsd_stamp_templates
from app.services.tsd_stamp_forensics import (
    CHANNEL_CODES,
    compute_forensic_fingerprint,
    embed_png_forensics,
    embed_svg_forensics,
    extract_pdf_forensics,
    extract_png_forensics,
    extract_svg_forensics,
    get_tenant_forensic_key,
    pack_forensic_packet,
    seal_pdf_bytes,
)
from app.services.tsd_stamp_receipts import (
    canonicalize_inserted_svg, issue_receipt, verify_receipt,
)


tsd_stamps_api = Blueprint("tsd_stamps_api", __name__, url_prefix="/api/tsd-stamps")


# ============================================================ helpers


def _actor():
    if not current_user.is_authenticated:
        abort(401)
    if current_user.organization_id is None:
        abort(403, description="organization_required")
    return current_user


def _emit(action: str, resource_id: int, outcome: str = "success",
          correlation_id: str | None = None) -> None:
    db.session.add(SecurityEvent(
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        action=(action or "tsd.stamp")[:100],
        resource_type="tsd_stamp",
        resource_id=resource_id,
        outcome=(outcome or "success")[:24],
        correlation_id=(correlation_id or uuid.uuid4().hex)[:64],
    ))


def _validate_svg(s: str, field: str = "svg") -> None:
    s = (s or "").strip()
    if not s.startswith("<svg") or not s.endswith("</svg>"):
        abort(400, description=f"{field}_invalid")
    if len(s) > 4 * 1024 * 1024:
        abort(400, description=f"{field}_too_large")


def _stamp_dimensions_mm(kind: str, layout: dict | None) -> tuple[float, float]:
    """Resolve physical artwork dimensions with legacy-layout compatibility.

    New layouts persist explicit width/height for every stamp shape. Older
    layouts used a diameter string for round stamps or ``WIDTHxHEIGHT`` for
    rectangular ones, with custom dimensions in separate fields.
    """
    layout = layout or {}

    def _number(value, fallback):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return fallback
        return min(300.0, max(5.0, number))

    if layout.get("width_mm") is not None and layout.get("height_mm") is not None:
        return (_number(layout["width_mm"], 59.0),
                _number(layout["height_mm"], 23.0))

    size_value = str(layout.get("size_value") or "").lower().replace("×", "x")
    if size_value == "custom":
        width = _number(layout.get("custom_w"), 42.0)
        return width, _number(layout.get("custom_h"), width)
    if "x" in size_value:
        try:
            width, height = size_value.split("x", 1)
            return _number(width, 59.0), _number(height, 23.0)
        except ValueError:
            pass

    shape = str(layout.get("shape") or "circle").lower()
    if kind in ("seal", "company_dated") and shape == "circle":
        diameter = _number(size_value or 42, 42.0)
        return diameter, diameter
    if kind in ("company_rect", "signature"):
        return (_number(layout.get("width_mm"), 80.0),
                _number(layout.get("height_mm"), 40.0))
    if kind in ("seal", "company_dated"):
        # Legacy non-circular seals were authored on a square canvas.
        side = _number(size_value or layout.get("custom_w"), 42.0)
        return side, _number(layout.get("custom_h"), side)
    return 59.0, 23.0


# ============================================================ CRUD


@tsd_stamps_api.route("/", methods=["GET"])
@login_required
def list_stamps():
    actor = _actor()
    q = TSDStamp.query.filter(
        TSDStamp.organization_id == actor.organization_id,
        TSDStamp.deleted_at.is_(None),
    )

    kind = (request.args.get("kind") or "").strip().lower()
    if kind and kind in TSD_STAMP_KINDS:
        q = q.filter(TSDStamp.kind == kind)

    search = (request.args.get("q") or "").strip()
    if search:
        q = q.filter(TSDStamp.name.ilike(f"%{search}%"))

    sort = (request.args.get("sort") or "recent").strip().lower()
    if sort == "name":
        q = q.order_by(TSDStamp.name.asc())
    elif sort == "usage":
        usage_sub = (
            db.session.query(
                TSDStampInsertion.stamp_id,
                func.count(TSDStampInsertion.id).label("n"),
            )
            .group_by(TSDStampInsertion.stamp_id)
            .subquery()
        )
        q = (q.outerjoin(usage_sub, usage_sub.c.stamp_id == TSDStamp.id)
             .order_by(func.coalesce(usage_sub.c.n, 0).desc(),
                       TSDStamp.updated_at.desc()))
    else:
        q = q.order_by(TSDStamp.updated_at.desc())

    rows = q.all()
    include_svg = (request.args.get("include_svg", "1") != "0")
    return jsonify([r.to_dict(include_svg=include_svg) for r in rows])


@tsd_stamps_api.route("/", methods=["POST"])
@login_required
def create_stamp():
    actor = _actor()
    payload = request.get_json(silent=True) or {}

    name = (payload.get("name") or "").strip()
    kind = (payload.get("kind") or "seal").lower()
    layout = payload.get("layout") or {}
    svg = (payload.get("svg") or "").strip()

    if not name:
        return jsonify({"error": "name_required"}), 400
    if len(name) > 120:
        return jsonify({"error": "name_too_long", "max": 120}), 400
    if kind not in TSD_STAMP_KINDS:
        return jsonify({"error": "invalid_kind",
                        "allowed": list(TSD_STAMP_KINDS)}), 400
    if not isinstance(layout, dict):
        return jsonify({"error": "layout_must_be_object"}), 400
    _validate_svg(svg)

    row = TSDStamp(
        organization_id=actor.organization_id,
        created_by_id=actor.id,
        name=name, kind=kind, layout=layout, svg=svg,
    )
    db.session.add(row)
    try:
        db.session.flush()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "duplicate_name"}), 409

    _emit("tsd.stamp_register", row.id, outcome=kind)
    db.session.commit()
    return jsonify(row.to_dict()), 201


@tsd_stamps_api.route("/<int:stamp_id>", methods=["PUT"])
@login_required
def update_stamp(stamp_id: int):
    actor = _actor()
    row = _owned_stamp(stamp_id, actor)
    # Published stamps are immutable — forces duplicate-on-edit UX.
    if row.status == "published":
        return jsonify({
            "error": "stamp_published",
            "message": "This stamp is published and cannot be edited. "
                       "Duplicate it to create a new editable draft.",
        }), 409
    payload = request.get_json(silent=True) or {}

    if "name" in payload:
        n = (payload["name"] or "").strip()
        if not n or len(n) > 120:
            return jsonify({"error": "name_invalid"}), 400
        row.name = n
    if "kind" in payload:
        if payload["kind"] not in TSD_STAMP_KINDS:
            return jsonify({"error": "invalid_kind"}), 400
        row.kind = payload["kind"]
    if "layout" in payload:
        if not isinstance(payload["layout"], dict):
            return jsonify({"error": "layout_must_be_object"}), 400
        row.layout = payload["layout"]
    if "svg" in payload:
        s = (payload["svg"] or "").strip()
        _validate_svg(s)
        row.svg = s

    _emit("tsd.stamp_update", row.id)
    db.session.commit()
    return jsonify(row.to_dict())


@tsd_stamps_api.route("/<int:stamp_id>", methods=["DELETE"])
@login_required
def delete_stamp(stamp_id: int):
    actor = _actor()
    row = _owned_stamp(stamp_id, actor)
    row.deleted_at = datetime.utcnow()
    _emit("tsd.stamp_delete", row.id)
    db.session.commit()
    return "", 204


def _owned_stamp(stamp_id: int, actor) -> TSDStamp:
    row = (
        TSDStamp.query
        .filter(TSDStamp.id == stamp_id,
                TSDStamp.organization_id == actor.organization_id,
                TSDStamp.deleted_at.is_(None))
        .first()
    )
    if row is None:
        abort(404)
    return row


# ============================================================ templates


@tsd_stamps_api.route("/devices", methods=["GET"])
@login_required
def list_devices():
    """Enumerate device profiles for the mechanism picker."""
    _actor()
    rows = DeviceProfile.query.order_by(
        DeviceProfile.mechanism, DeviceProfile.manufacturer, DeviceProfile.model
    ).all()
    return jsonify({"devices": [r.to_dict() for r in rows]})


@tsd_stamps_api.route("/templates", methods=["GET"])
@login_required
def list_templates():
    _actor()
    return jsonify({"templates": tsd_stamp_templates.list_templates()})


@tsd_stamps_api.route("/from-template/<string:slug>", methods=["POST"])
@login_required
def create_from_template(slug: str):
    actor = _actor()
    tpl = tsd_stamp_templates.get_template(slug)
    if tpl is None:
        return jsonify({"error": "template_not_found", "slug": slug}), 404

    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or tpl.name).strip()
    if not name:
        return jsonify({"error": "name_required"}), 400

    row = TSDStamp(
        organization_id=actor.organization_id,
        created_by_id=actor.id,
        name=name,
        kind=tpl.kind,
        layout=copy.deepcopy(tpl.layout),
        svg=tpl.svg,
    )
    db.session.add(row)
    try:
        db.session.flush()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "duplicate_name"}), 409
    _emit("tsd.stamp_register", row.id, outcome=f"template:{slug}")
    db.session.commit()
    return jsonify(row.to_dict()), 201


# ============================================================ duplicate


@tsd_stamps_api.route("/<int:stamp_id>/duplicate", methods=["POST"])
@login_required
def duplicate_stamp(stamp_id: int):
    actor = _actor()
    src = _owned_stamp(stamp_id, actor)

    # Find a "Copy of X" name that doesn't collide.
    base_name = (request.get_json(silent=True) or {}).get("name") or f"Copy of {src.name}"
    base_name = base_name.strip()[:115]
    candidate = base_name
    n = 2
    while TSDStamp.query.filter(
        TSDStamp.organization_id == actor.organization_id,
        TSDStamp.deleted_at.is_(None),
        TSDStamp.name == candidate,
    ).first() is not None:
        candidate = f"{base_name} ({n})"
        n += 1
        if n > 50:
            return jsonify({"error": "duplicate_exhausted"}), 409

    row = TSDStamp(
        organization_id=actor.organization_id,
        created_by_id=actor.id,
        name=candidate,
        kind=src.kind,
        layout=copy.deepcopy(src.layout),
        svg=src.svg,
    )
    db.session.add(row)
    db.session.flush()
    _emit("tsd.stamp_register", row.id, outcome=f"duplicate_of:{src.id}")
    db.session.commit()
    return jsonify(row.to_dict()), 201


# ============================================================ receipts & forensics


def _infer_channel(context_label: str | None, document_id: int | None) -> str:
    lbl = (context_label or "").lower()
    if lbl.startswith("pdf export") or "export.pdf" in lbl or "[pdf]" in lbl:
        return "pdf_export"
    if lbl.startswith("png export") or "[png]" in lbl:
        return "png_export"
    if lbl.startswith("svg export") or "[svg]" in lbl:
        return "svg_export"
    if document_id:
        return "tsd_document"
    return "tsd_document"


def _user_display(u: User | None, fallback_id: int | None) -> dict:
    if u is None:
        return {
            "id": fallback_id,
            "name": f"User #{fallback_id}" if fallback_id else "System",
            "email": None,
        }
    full = (u.get_full_name() or "").strip() if hasattr(u, "get_full_name") else ""
    return {
        "id": u.id,
        "name": full or u.username or u.email or f"User #{u.id}",
        "email": u.email,
    }


def _enrich_insertions(
    rows: list[TSDStampInsertion],
    organization_id: int,
) -> list[dict]:
    """Attach user names, stamp names, document titles, forensic fingerprints & verify URLs."""
    if not rows:
        return []
    from flask import url_for

    forensic_key = get_tenant_forensic_key(organization_id)
    user_ids = {r.placed_by_id for r in rows if r.placed_by_id}
    stamp_ids = {r.stamp_id for r in rows if r.stamp_id}
    doc_ids = {r.document_id for r in rows if r.document_id}

    users = {
        u.id: u
        for u in User.query.filter(User.id.in_(list(user_ids) or [-1])).all()
    }
    stamps = {
        s.id: s
        for s in TSDStamp.query.filter(TSDStamp.id.in_(list(stamp_ids) or [-1])).all()
    }
    docs = {
        d.id: d
        for d in TSDocument.query.filter(TSDocument.id.in_(list(doc_ids) or [-1])).all()
    }

    out: list[dict] = []
    for r in rows:
        d = r.to_dict()
        uinfo = _user_display(users.get(r.placed_by_id), r.placed_by_id)
        st = stamps.get(r.stamp_id)
        doc = docs.get(r.document_id) if r.document_id else None
        fp = compute_forensic_fingerprint(
            forensic_key,
            receipt_id=r.id,
            stamp_id=r.stamp_id,
            nonce=r.nonce,
        )
        d["placed_by_name"] = uinfo["name"]
        d["placed_by_email"] = uinfo["email"]
        d["stamp_name"] = st.name if st else f"Stamp #{r.stamp_id}"
        d["stamp_kind"] = st.kind if st else None
        d["document_title"] = doc.title if doc else None
        d["channel"] = _infer_channel(r.context_label, r.document_id)
        d["forensic_fingerprint"] = fp
        d["context_hash_prefix"] = (r.context_hash or "")[:16]
        d["verify_url"] = url_for(
            "stamp_verify_public.verify_public",
            receipt_id=r.id,
            nonce=r.nonce,
            _external=True,
        )
        out.append(d)
    return out


@tsd_stamps_api.route("/<int:stamp_id>/receipt", methods=["POST"])
@login_required
def mint_receipt(stamp_id: int):
    actor = _actor()
    row = _owned_stamp(stamp_id, actor)
    payload = request.get_json(silent=True) or {}

    import re as _re_rcpt
    svg = (payload.get("svg") or row.svg or "").strip()
    svg = _re_rcpt.sub(
        r'font-family="(.+?)"(?=\s+[a-zA-Z_-]+=|\s*/?>)',
        lambda m: 'font-family="' + m.group(1).replace('"', "'") + '"',
        svg,
    )
    _validate_svg(svg, field="context_svg")
    svg = canonicalize_inserted_svg(svg)

    document_id = payload.get("document_id")
    if document_id is not None:
        try:
            document_id = int(document_id)
        except (TypeError, ValueError):
            return jsonify({"error": "document_id_invalid"}), 400
    channel = (payload.get("channel") or "tsd_document").strip().lower()
    if channel not in CHANNEL_CODES:
        channel = "tsd_document"
    raw_label = (payload.get("context_label") or "").strip()
    if not raw_label:
        if channel == "svg_export":
            raw_label = f"SVG export · {row.name}"
        elif channel == "png_export":
            raw_label = f"PNG export · {row.name}"
        elif channel == "pdf_export":
            raw_label = f"PDF export · {row.name}"
    context_label = raw_label[:200] or None

    receipt = issue_receipt(
        organization_id=actor.organization_id,
        stamp=row,
        placed_by_id=actor.id,
        document_id=document_id,
        context_label=context_label,
        context_svg=svg,
    )

    forensic_key = get_tenant_forensic_key(actor.organization_id)
    sealed_svg, forensic_fp, _ = embed_svg_forensics(
        svg,
        forensic_key,
        organization_id=actor.organization_id,
        stamp_id=row.id,
        receipt_id=receipt.id,
        placed_by_id=actor.id,
        document_id=document_id,
        placed_at=receipt.placed_at,
        nonce=receipt.nonce,
        channel=channel,
    )
    _emit(
        "tsd.stamp_insert",
        row.id,
        outcome=f"receipt:{receipt.id}",
    )
    db.session.commit()

    from flask import url_for
    verify_url = url_for(
        "stamp_verify_public.verify_public",
        receipt_id=receipt.id, nonce=receipt.nonce, _external=True,
    )
    qr_url = url_for(
        "stamp_verify_public.qr_svg",
        receipt_id=receipt.id, nonce=receipt.nonce, _external=True,
    )
    return jsonify({
        "receipt_id": receipt.id,
        "nonce": receipt.nonce,
        "placed_at": receipt.placed_at.isoformat(),
        "placed_by_id": receipt.placed_by_id,
        "stamp_id": receipt.stamp_id,
        "document_id": receipt.document_id,
        "channel": channel,
        "forensic_fingerprint": forensic_fp,
        "security_layers": [
            "hmac_sha256_receipt",
            "vector_micro_constellation",
            "vector_micro_path",
            "covert_micro_text_fiber",
        ],
        "sealed_svg": sealed_svg,
        "verify_url": verify_url,
        "qr_url": qr_url,
    }), 201


@tsd_stamps_api.route("/<int:stamp_id>/export-sealed-png", methods=["POST"])
@login_required
def export_sealed_png(stamp_id: int):
    """Mint a tracked receipt & embed Layer 3 keyed raster steganography into a PNG."""
    import base64
    from io import BytesIO
    from flask import send_file

    actor = _actor()
    row = _owned_stamp(stamp_id, actor)

    png_bytes: bytes | None = None
    dpi = 300
    context_label = None

    if "file" in request.files:
        png_bytes = request.files["file"].read()
        dpi = int(request.form.get("dpi") or 300)
        context_label = (request.form.get("context_label") or "").strip() or None
    else:
        payload = request.get_json(silent=True) or {}
        b64 = payload.get("png_base64") or ""
        if "," in b64 and b64.startswith("data:"):
            b64 = b64.split(",", 1)[1]
        if b64:
            try:
                png_bytes = base64.b64decode(b64)
            except Exception:
                return jsonify({"error": "invalid_png_base64"}), 400
        try:
            dpi = int(payload.get("dpi") or 300)
        except (TypeError, ValueError):
            dpi = 300
        context_label = (payload.get("context_label") or "").strip() or None

    if not png_bytes or len(png_bytes) > 12 * 1024 * 1024:
        return jsonify({"error": "png_required_or_too_large"}), 400

    canonical_svg = canonicalize_inserted_svg(row.svg or "")
    label = context_label or f"PNG export ({dpi} dpi) · {row.name}"
    receipt = issue_receipt(
        organization_id=actor.organization_id,
        stamp=row,
        placed_by_id=actor.id,
        document_id=None,
        context_label=label[:200],
        context_svg=canonical_svg,
    )

    forensic_key = get_tenant_forensic_key(actor.organization_id)
    try:
        sealed_png, forensic_fp, _ = embed_png_forensics(
            png_bytes,
            forensic_key,
            organization_id=actor.organization_id,
            stamp_id=row.id,
            receipt_id=receipt.id,
            placed_by_id=actor.id,
            document_id=None,
            placed_at=receipt.placed_at,
            nonce=receipt.nonce,
            channel="png_export",
        )
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "png_forensic_seal_failed", "detail": str(e)}), 400

    _emit(
        "tsd.stamp_export_png",
        row.id,
        outcome=f"receipt:{receipt.id}",
    )
    db.session.commit()

    resp = send_file(
        BytesIO(sealed_png),
        mimetype="image/png",
        as_attachment=True,
        download_name=f"{row.name}-{dpi}dpi-sealed.png",
    )
    resp.headers["X-TSD-Receipt-Id"] = str(receipt.id)
    resp.headers["X-TSD-Forensic-Fingerprint"] = forensic_fp
    resp.headers["X-TSD-Receipt-Nonce"] = receipt.nonce
    return resp


@tsd_stamps_api.route("/forensic-verify", methods=["POST"])
@login_required
def forensic_verify_api():
    """Inspect an SVG, PNG, or PDF for hidden TSD-only covert security features
    and return the full provenance, tamper status, and audit trail."""
    actor = _actor()
    forensic_key = get_tenant_forensic_key(actor.organization_id)

    file_kind = "svg"
    extracted: dict = {}
    raw_svg: str | None = None

    if "file" in request.files and request.files["file"].filename:
        f = request.files["file"]
        fname = (f.filename or "").lower()
        data = f.read(16 * 1024 * 1024 + 1)
        if len(data) > 16 * 1024 * 1024:
            return jsonify({"error": "file_too_large"}), 400
        if fname.endswith(".png") or data.startswith(b"\x89PNG\r\n\x1a\n"):
            file_kind = "png"
            try:
                extracted = extract_png_forensics(data, forensic_key)
            except Exception as e:
                return jsonify({"error": "png_parse_failed", "detail": str(e)}), 400
        elif fname.endswith(".pdf") or data.startswith(b"%PDF"):
            file_kind = "pdf"
            try:
                extracted = extract_pdf_forensics(data, forensic_key)
            except Exception as e:
                return jsonify({"error": "pdf_parse_failed", "detail": str(e)}), 400
        else:
            file_kind = "svg"
            raw_svg = data.decode("utf-8", errors="replace")
            extracted = extract_svg_forensics(raw_svg, forensic_key)
    else:
        payload = request.get_json(silent=True) or {}
        raw_svg = (payload.get("svg") or "").strip()
        if not raw_svg:
            return jsonify({"error": "file_or_svg_required"}), 400
        file_kind = "svg"
        extracted = extract_svg_forensics(raw_svg, forensic_key)

    fp_payload = extracted.get("payload")
    layers = list(extracted.get("layers_detected") or [])
    overt_rid = extracted.get("overt_receipt_id")
    overt_nonce = extracted.get("overt_nonce")

    receipt_id = fp_payload.receipt_id if fp_payload else overt_rid
    if not receipt_id:
        return jsonify({
            "authentic": False,
            "verdict": "UNVERIFIED",
            "reason": "no_tsd_forensic_mark_detected",
            "file_kind": file_kind,
            "layers_detected": layers,
            "micro_text_fingerprint": extracted.get("micro_text_fingerprint"),
        })

    row = db.session.get(TSDStampInsertion, int(receipt_id))
    if row is None or row.organization_id != actor.organization_id:
        return jsonify({
            "authentic": False,
            "verdict": "FOREIGN_OR_UNKNOWN",
            "reason": "receipt_not_found_in_tenant",
            "file_kind": file_kind,
            "layers_detected": layers,
            "forensic_payload": fp_payload.to_dict() if fp_payload else None,
        })

    # Verify the authoritative server-side HMAC receipt
    check_nonce = overt_nonce or row.nonce
    if fp_payload and not row.nonce.startswith(fp_payload.nonce_prefix):
        return jsonify({
            "authentic": False,
            "verdict": "TAMPERED",
            "reason": "forensic_nonce_prefix_mismatch",
            "file_kind": file_kind,
            "layers_detected": layers,
        })

    canonical_for_hash = canonicalize_inserted_svg(raw_svg) if raw_svg else None
    vr = verify_receipt(
        organization_id=actor.organization_id,
        receipt_id=row.id,
        nonce=check_nonce,
        context_svg=canonical_for_hash,
    )

    expected_fp = compute_forensic_fingerprint(
        forensic_key,
        receipt_id=row.id,
        stamp_id=row.stamp_id,
        nonce=row.nonce,
    )
    fp_matches = (
        extracted.get("micro_text_fingerprint") is None
        or extracted.get("micro_text_fingerprint") == expected_fp
    )
    if vr.get("valid"):
        layers.append("hmac_sha256_receipt")

    context_intact = vr.get("context_intact")
    if not vr.get("valid"):
        verdict = "INVALID"
        authentic = False
    elif row.revoked_at is not None:
        verdict = "REVOKED"
        authentic = False
    elif context_intact is False or not fp_matches:
        verdict = "TAMPERED"
        authentic = False
    else:
        verdict = "AUTHENTIC"
        authentic = True

    stamp = db.session.get(TSDStamp, row.stamp_id)
    placer = db.session.get(User, row.placed_by_id)
    doc = db.session.get(TSDocument, row.document_id) if row.document_id else None

    events = (
        SecurityEvent.query
        .filter(
            SecurityEvent.organization_id == actor.organization_id,
            SecurityEvent.resource_type == "tsd_stamp",
            SecurityEvent.resource_id == row.stamp_id,
        )
        .order_by(SecurityEvent.created_at.desc())
        .limit(20)
        .all()
    )
    ev_user_ids = {e.actor_id for e in events if e.actor_id}
    ev_users = {
        u.id: u
        for u in User.query.filter(User.id.in_(list(ev_user_ids) or [-1])).all()
    }

    _emit(
        "tsd.stamp_forensic_verify",
        row.stamp_id,
        outcome=f"r:{row.id}:{verdict[:12]}",
    )
    db.session.commit()

    from flask import url_for
    verify_url = url_for(
        "stamp_verify_public.verify_public",
        receipt_id=row.id,
        nonce=row.nonce,
        _external=True,
    )

    return jsonify({
        "authentic": authentic,
        "verdict": verdict,
        "reason": vr.get("reason") if not vr.get("valid") else (
            "receipt_revoked" if row.revoked_at else (
                "artwork_modified_after_issuance" if context_intact is False else None
            )
        ),
        "file_kind": file_kind,
        "layers_detected": sorted(set(layers)),
        "covert_verified": fp_payload is not None,
        "context_intact": context_intact,
        "fingerprint_match": fp_matches,
        "forensic_fingerprint": expected_fp,
        "forensic_payload": fp_payload.to_dict() if fp_payload else None,
        "receipt": {
            "id": row.id,
            "nonce": row.nonce,
            "placed_at": row.placed_at.isoformat() if row.placed_at else None,
            "context_label": row.context_label,
            "channel": fp_payload.channel if fp_payload else _infer_channel(row.context_label, row.document_id),
            "context_hash": row.context_hash,
            "revoked": row.revoked_at is not None,
            "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
            "revoked_reason": row.revoked_reason,
            "verify_url": verify_url,
        },
        "stamp": {
            "id": stamp.id if stamp else row.stamp_id,
            "name": stamp.name if stamp else f"Stamp #{row.stamp_id}",
            "kind": stamp.kind if stamp else None,
            "status": (stamp.status or "draft") if stamp else None,
        },
        "actor": _user_display(placer, row.placed_by_id),
        "document": {
            "id": doc.id,
            "title": doc.title,
        } if doc else None,
        "audit_trail": [{
            "action": e.action,
            "outcome": e.outcome,
            "actor_id": e.actor_id,
            "actor_name": _user_display(ev_users.get(e.actor_id), e.actor_id)["name"],
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "correlation_id": e.correlation_id,
        } for e in events],
    })


@tsd_stamps_api.route("/verify-receipt", methods=["POST"])
@login_required
def verify_receipt_api():
    actor = _actor()
    payload = request.get_json(silent=True) or {}
    receipt_id = payload.get("receipt_id")
    nonce = payload.get("nonce")
    context_svg = payload.get("svg")
    if receipt_id is None or nonce is None:
        return jsonify({"error": "receipt_id_and_nonce_required"}), 400
    try:
        receipt_id = int(receipt_id)
    except (TypeError, ValueError):
        return jsonify({"error": "receipt_id_invalid"}), 400

    covert_layers: list[str] = []
    if context_svg:
        try:
            fkey = get_tenant_forensic_key(actor.organization_id)
            fx = extract_svg_forensics(context_svg, fkey)
            if fx.get("found"):
                covert_layers = list(fx.get("layers_detected") or [])
        except Exception:
            pass
        context_svg = canonicalize_inserted_svg(context_svg)

    result = verify_receipt(
        organization_id=actor.organization_id,
        receipt_id=receipt_id,
        nonce=str(nonce),
        context_svg=context_svg,
    )
    if result.get("valid"):
        result["covert_layers"] = covert_layers
        try:
            fkey = get_tenant_forensic_key(actor.organization_id)
            result["forensic_fingerprint"] = compute_forensic_fingerprint(
                fkey,
                receipt_id=int(receipt_id),
                stamp_id=int(result["stamp_id"]),
                nonce=str(nonce),
            )
        except Exception:
            pass
    return jsonify(result)


@tsd_stamps_api.route("/insertions", methods=["GET"])
@login_required
def list_org_insertions():
    """Organization-wide traceable stamp usage ledger with filtering."""
    from datetime import timedelta

    actor = _actor()
    q = TSDStampInsertion.query.filter(
        TSDStampInsertion.organization_id == actor.organization_id
    )
    stamp_id = request.args.get("stamp_id")
    if stamp_id:
        try:
            q = q.filter(TSDStampInsertion.stamp_id == int(stamp_id))
        except ValueError:
            return jsonify({"error": "invalid_stamp_id"}), 400

    status_filter = (request.args.get("status") or "").lower().strip()
    if status_filter == "active":
        q = q.filter(TSDStampInsertion.revoked_at.is_(None))
    elif status_filter == "revoked":
        q = q.filter(TSDStampInsertion.revoked_at.isnot(None))

    days = request.args.get("days")
    if days:
        try:
            d_int = max(1, min(365, int(days)))
            q = q.filter(TSDStampInsertion.placed_at >= datetime.utcnow() - timedelta(days=d_int))
        except ValueError:
            pass

    limit = 200
    try:
        limit = max(1, min(500, int(request.args.get("limit", 200))))
    except ValueError:
        pass

    rows = q.order_by(TSDStampInsertion.placed_at.desc()).limit(limit).all()
    enriched = _enrich_insertions(rows, actor.organization_id)

    search = (request.args.get("q") or "").strip().lower()
    if search:
        enriched = [
            it for it in enriched
            if search in (it.get("stamp_name") or "").lower()
            or search in (it.get("placed_by_name") or "").lower()
            or search in (it.get("context_label") or "").lower()
            or search in (it.get("document_title") or "").lower()
            or search in (it.get("forensic_fingerprint") or "").lower()
            or search == str(it.get("id"))
        ]

    return jsonify({
        "count": len(enriched),
        "insertions": enriched,
    })


@tsd_stamps_api.route("/<int:stamp_id>/insertions", methods=["GET"])
@login_required
def list_insertions(stamp_id: int):
    actor = _actor()
    _owned_stamp(stamp_id, actor)
    rows = (
        TSDStampInsertion.query
        .filter(TSDStampInsertion.stamp_id == stamp_id,
                TSDStampInsertion.organization_id == actor.organization_id)
        .order_by(TSDStampInsertion.placed_at.desc())
        .limit(500)
        .all()
    )
    enriched = _enrich_insertions(rows, actor.organization_id)
    return jsonify({
        "stamp_id": stamp_id,
        "count": len(enriched),
        "insertions": enriched,
    })


@tsd_stamps_api.route("/<int:stamp_id>/insertions/<int:receipt_id>/revoke",
                      methods=["POST"])
@login_required
def revoke_insertion(stamp_id: int, receipt_id: int):
    actor = _actor()
    _owned_stamp(stamp_id, actor)
    row = db.session.get(TSDStampInsertion, receipt_id)
    if row is None or row.organization_id != actor.organization_id \
       or row.stamp_id != stamp_id:
        abort(404)
    payload = request.get_json(silent=True) or {}
    row.revoked_at = datetime.utcnow()
    row.revoked_reason = (payload.get("reason") or "").strip()[:200] or "user_request"
    _emit("tsd.stamp_insert_revoke", stamp_id, outcome=f"receipt:{row.id}")
    db.session.commit()
    return jsonify(row.to_dict())


# ============================================================ audit


@tsd_stamps_api.route("/<int:stamp_id>/status", methods=["POST"])
@login_required
def set_stamp_status(stamp_id: int):
    """Transition a stamp between draft → review → published → archived."""
    actor = _actor()
    row = _owned_stamp(stamp_id, actor)
    payload = request.get_json(silent=True) or {}
    target = (payload.get("status") or "").lower()

    ALLOWED = {
        "draft":     {"review", "archived"},
        "review":    {"draft", "published", "archived"},
        "published": {"archived"},
        "archived":  {"draft"},
    }
    current = row.status or "draft"
    if target not in ALLOWED.get(current, set()):
        return jsonify({
            "error": "invalid_transition",
            "message": f"Cannot move from '{current}' to '{target}'.",
            "allowed": sorted(ALLOWED.get(current, [])),
        }), 400

    row.status = target
    if target == "published":
        from datetime import datetime
        row.published_at = datetime.utcnow()
        row.published_by_id = actor.id
        # Snapshot the design into a tsd_stamp_revisions row — the row
        # is immutable once written, so audits + inserted receipts can
        # always point at exactly what was published.
        from sqlalchemy import func as _func
        latest = db.session.query(_func.max(TSDStampRevision.version)) \
            .filter(TSDStampRevision.stamp_id == row.id).scalar() or 0
        db.session.add(TSDStampRevision(
            stamp_id=row.id,
            version=latest + 1,
            created_by_id=actor.id,
            status_at_snapshot="published",
            layout=row.layout,
            svg=row.svg,
            name_at_snapshot=row.name,
            notes=payload.get("notes"),
        ))
    if target == "draft":
        row.published_at = None
        row.published_by_id = None

    _emit(f"tsd.stamp_status_{target}", row.id, outcome=f"from:{current}")
    db.session.commit()
    return jsonify(row.to_dict(include_svg=False))


def _extract_colors(svg_src: str) -> list[str]:
    """Pull distinct `#RRGGBB` strokes + fills out of an SVG string."""
    import re as _re

    colors: dict[str, bool] = {}
    for m in _re.finditer(r'(?:stroke|fill)="(#[0-9A-Fa-f]{3,6})"', svg_src):
        c = m.group(1).upper()
        if len(c) == 4:   # #RGB → #RRGGBB
            c = "#" + "".join(ch * 2 for ch in c[1:])
        if c in ("#NONE", "#FFFFFF"):
            continue
        colors[c] = True
    return list(colors.keys())


@tsd_stamps_api.route("/<int:stamp_id>/zones", methods=["GET"])
@login_required
def list_zones(stamp_id: int):
    """Detect ink colour zones for production-separation (§13.1.5)."""
    actor = _actor()
    row = _owned_stamp(stamp_id, actor)
    cols = _extract_colors(row.svg or "")
    return jsonify({
        "stamp_id": stamp_id,
        "zones": [{"color": c, "name": f"Zone {chr(65 + i)}"}
                  for i, c in enumerate(cols)],
    })


@tsd_stamps_api.route("/<int:stamp_id>/export.pdf", methods=["GET"])
@login_required
def export_pdf(stamp_id: int):
    """Rasterise the stamp into a single-page PDF sized to its physical mm.

    Query parameters (§13 production options):
      - mirror=1               Horizontally mirror the output (rubber plates)
      - polarity=negative      Swap ink / background for photopolymer exposure
      - grayscale=1            Convert to pure grayscale output
    """
    actor = _actor()
    row = _owned_stamp(stamp_id, actor)

    try:
        from io import BytesIO
        from reportlab.graphics import renderPDF
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas as _pdfcanvas
        from svglib.svglib import svg2rlg
    except Exception as e:  # pragma: no cover
        return jsonify({"error": "pdf_renderer_unavailable", "detail": str(e)}), 500

    mirror    = request.args.get("mirror") in ("1", "true", "yes")
    polarity  = (request.args.get("polarity") or "positive").lower()
    grayscale = request.args.get("grayscale") in ("1", "true", "yes")
    zone      = (request.args.get("zone") or "").upper().strip()

    layout = row.layout or {}
    w_mm, h_mm = _stamp_dimensions_mm(row.kind, layout)

    svg_src = row.svg

    # Track every PDF export as a signed, forensically sealed receipt (graceful fallback if key unavailable).
    canonical_svg = canonicalize_inserted_svg(svg_src or "")
    pdf_opts = []
    if zone: pdf_opts.append(f"zone={zone}")
    if mirror: pdf_opts.append("mirror")
    if polarity == "negative": pdf_opts.append("negative")
    if grayscale: pdf_opts.append("grayscale")
    pdf_ctx = f"PDF export ({', '.join(pdf_opts) or 'standard'}) · {row.name}"
    receipt = None
    forensic_fp = None
    forensic_packet = None
    try:
        receipt = issue_receipt(
            organization_id=actor.organization_id,
            stamp=row,
            placed_by_id=actor.id,
            document_id=None,
            context_label=pdf_ctx[:200],
            context_svg=canonical_svg,
        )
        forensic_key = get_tenant_forensic_key(actor.organization_id)
        sealed_svg, forensic_fp, forensic_packet = embed_svg_forensics(
            canonical_svg,
            forensic_key,
            organization_id=actor.organization_id,
            stamp_id=row.id,
            receipt_id=receipt.id,
            placed_by_id=actor.id,
            document_id=None,
            placed_at=receipt.placed_at,
            nonce=receipt.nonce,
            channel="pdf_export",
        )
        svg_src = sealed_svg
    except Exception:
        db.session.rollback()
        svg_src = canonical_svg or (row.svg or "")

    # Zone separation (§13.1.5): render only elements matching the picked
    # ink colour, hide all other coloured strokes/fills. This is the
    # per-plate artwork for multi-colour production.
    if zone and zone.startswith("#"):
        import re as _re
        def _zone_filter(m):
            attr, col = m.group(1), m.group(2).upper()
            if len(col) == 4:
                col = "#" + "".join(ch * 2 for ch in col[1:])
            # Keep matching zone; non-matching coloured strokes/fills → transparent.
            if col == zone or col == "#FFFFFF":
                return m.group(0)
            if attr.startswith("fill"):
                return 'fill="none"'
            return 'stroke="none"'
        svg_src = _re.sub(r'(stroke="|fill=")(#[0-9A-Fa-f]{3,6})',
                          _zone_filter, svg_src)

    # Polarity negative: flood a black rect behind + invert stroke/fill colours
    # to white so photopolymer plates expose correctly.
    if polarity == "negative":
        import re as _re
        # Insert black background rect as the first child of <svg ...>
        viewbox = _re.search(r'viewBox="([^"]+)"', svg_src)
        bgrect = ''
        if viewbox:
            vb = viewbox.group(1).split()
            if len(vb) == 4:
                bgrect = f'<rect x="{vb[0]}" y="{vb[1]}" width="{vb[2]}" height="{vb[3]}" fill="black"/>'
        svg_src = _re.sub(r'(<svg\b[^>]*>)', r'\1' + bgrect, svg_src, count=1)
        # Swap non-white strokes/fills to white; leave 'none' and already-white alone.
        svg_src = _re.sub(r'(stroke="|fill=")(#[0-9A-Fa-f]{3,6})',
                          lambda m: m.group(1) + '#FFFFFF' if m.group(2).lower() != '#ffffff' else m.group(0),
                          svg_src)

    if grayscale:
        import re as _re
        def to_gray(m):
            hex_ = m.group(2).lstrip('#')
            if len(hex_) == 3: hex_ = ''.join(c*2 for c in hex_)
            r, g, b = int(hex_[0:2], 16), int(hex_[2:4], 16), int(hex_[4:6], 16)
            y = round(0.299 * r + 0.587 * g + 0.114 * b)
            return m.group(1) + f'#{y:02X}{y:02X}{y:02X}'
        svg_src = _re.sub(r'(stroke="|fill=")(#[0-9A-Fa-f]{3,6})', to_gray, svg_src)

    import base64 as _b64_pdf
    import re as _re_pdf
    # Repair any nested double-quotes inside font-family="..." (e.g. legacy saved stamps)
    svg_src = _re_pdf.sub(
        r'font-family="(.+?)"(?=\s+[a-zA-Z_-]+=|\s*/?>)',
        lambda m: 'font-family="' + m.group(1).replace('"', "'") + '"',
        svg_src,
    )
    # Ensure xmlns + xlink namespace for svglib compatibility
    if 'xmlns="http://www.w3.org/2000/svg"' not in svg_src:
        svg_src = _re_pdf.sub(r'<svg\b', '<svg xmlns="http://www.w3.org/2000/svg"', svg_src, count=1)

    def _flatten_rgba_data_uri(data_uri: str, bg_rgb: tuple[int, int, int]) -> str:
        """Flatten RGBA/palette-transparent PNG/WEBP data URIs onto bg_rgb so ReportLab never renders black boxes."""
        if not data_uri.startswith("data:image/") or ";base64," not in data_uri:
            return data_uri
        try:
            from PIL import Image as _PILImage
            head, b64_part = data_uri.split(";base64,", 1)
            mime = head[5:].lower()
            if "svg" in mime:
                return data_uri
            raw = _b64_pdf.b64decode(b64_part)
            with _PILImage.open(BytesIO(raw)) as im:
                if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                    rgba = im.convert("RGBA")
                    bg = _PILImage.new("RGBA", rgba.size, (*bg_rgb, 255))
                    flat = _PILImage.alpha_composite(bg, rgba).convert("RGB")
                else:
                    flat = im.convert("RGB")
                out_img = BytesIO()
                flat.save(out_img, format="PNG")
                return "data:image/png;base64," + _b64_pdf.b64encode(out_img.getvalue()).decode("ascii")
        except Exception:
            return data_uri

    img_bg_rgb = (0, 0, 0) if polarity == "negative" else (255, 255, 255)

    def _normalize_image_tag(m):
        tag = m.group(0)
        if 'xlink:href=' in tag:
            # Strip bare href= so XML parser never sees duplicate href/xlink:href
            tag = _re_pdf.sub(r'\s+href="[^"]*"', '', tag)
        else:
            tag = _re_pdf.sub(r'\bhref="', 'xlink:href="', tag, count=1)
        tag = _re_pdf.sub(
            r'xlink:href="(data:image/[^"]+)"',
            lambda dm: 'xlink:href="' + _flatten_rgba_data_uri(dm.group(1), img_bg_rgb) + '"',
            tag,
        )
        return tag

    def _normalize_textpath_tag(m):
        tag = m.group(0)
        if 'xlink:href=' in tag:
            return _re_pdf.sub(r'\s+href="[^"]*"', '', tag)
        return _re_pdf.sub(r'\bhref="', 'xlink:href="', tag, count=1)

    svg_for_rlg = _re_pdf.sub(r'<image\b[^>]*/?>', _normalize_image_tag, svg_src)
    svg_for_rlg = _re_pdf.sub(r'<textPath\b[^>]*>', _normalize_textpath_tag, svg_for_rlg)
    if 'xlink:href=' in svg_for_rlg and 'xmlns:xlink=' not in svg_for_rlg:
        svg_for_rlg = _re_pdf.sub(r'<svg\b', '<svg xmlns:xlink="http://www.w3.org/1999/xlink"', svg_for_rlg, count=1)

    no_filter = _re_pdf.sub(
        r'<filter\b[^>]*>.*?</filter>', '',
        _re_pdf.sub(r'\sfilter="url\([^"]*\)"', '', svg_for_rlg),
        flags=_re_pdf.DOTALL,
    )
    no_img = _re_pdf.sub(r'<image\b[^>]*/?>', '', no_filter)

    page_w = w_mm * mm
    page_h = h_mm * mm
    buf = None
    render_err = None
    for candidate in (svg_for_rlg, no_filter, no_img):
        try:
            drawing = svg2rlg(BytesIO(candidate.encode("utf-8")))
            if drawing is None or not drawing.width or not drawing.height:
                continue
            scale_x = page_w / drawing.width
            scale_y = page_h / drawing.height
            if mirror:
                drawing.translate(drawing.width, 0)
                drawing.scale(-scale_x, scale_y)
            else:
                drawing.scale(scale_x, scale_y)
            drawing.width, drawing.height = page_w, page_h
            tmp_buf = BytesIO()
            c = _pdfcanvas.Canvas(tmp_buf, pagesize=(page_w, page_h))
            renderPDF.draw(drawing, c, 0, 0)
            c.showPage()
            c.save()
            buf = tmp_buf
            break
        except Exception as e:
            render_err = e
            buf = None

    if buf is None:
        return jsonify({"error": "svg_parse_failed", "detail": str(render_err or "empty_drawing")}), 500

    # Attach Layer 4 encrypted PDF forensic seal
    if forensic_packet and forensic_fp:
        try:
            sealed_pdf = seal_pdf_bytes(buf.getvalue(), forensic_packet, forensic_fp)
            out_buf = BytesIO(sealed_pdf)
        except Exception:
            buf.seek(0)
            out_buf = buf
    else:
        buf.seek(0)
        out_buf = buf

    if receipt is not None:
        try:
            _emit(
                "tsd.stamp_export_pdf",
                row.id,
                outcome=f"receipt:{receipt.id}",
            )
            db.session.commit()
        except Exception:
            db.session.rollback()

    from flask import send_file
    # Name the file descriptively so a user export doesn't overwrite a plate.
    suffix = []
    if zone: suffix.append("zone-" + zone.lstrip("#"))
    if mirror: suffix.append("mirror")
    if polarity == "negative": suffix.append("neg")
    if grayscale: suffix.append("gray")
    tag = ("_" + "_".join(suffix)) if suffix else ""
    out_buf.seek(0)
    resp = send_file(out_buf, mimetype="application/pdf",
                     as_attachment=True,
                     download_name=f"{row.name}{tag}.pdf")
    if receipt is not None:
        resp.headers["X-TSD-Receipt-Id"] = str(receipt.id)
        resp.headers["X-TSD-Receipt-Nonce"] = receipt.nonce
    if forensic_fp:
        resp.headers["X-TSD-Forensic-Fingerprint"] = forensic_fp
    return resp


@tsd_stamps_api.route("/<int:stamp_id>/revisions", methods=["GET"])
@login_required
def list_revisions(stamp_id: int):
    """List immutable published-revision snapshots for this stamp."""
    actor = _actor()
    _owned_stamp(stamp_id, actor)
    rows = (
        TSDStampRevision.query
        .filter(TSDStampRevision.stamp_id == stamp_id)
        .order_by(TSDStampRevision.version.desc())
        .all()
    )
    return jsonify({
        "stamp_id": stamp_id,
        "count": len(rows),
        "revisions": [r.to_dict(include_svg=False) for r in rows],
    })


@tsd_stamps_api.route("/<int:stamp_id>/revisions/<int:revision_id>", methods=["GET"])
@login_required
def get_revision(stamp_id: int, revision_id: int):
    """Fetch a single frozen revision (including its SVG for display)."""
    actor = _actor()
    _owned_stamp(stamp_id, actor)
    rev = db.session.get(TSDStampRevision, revision_id)
    if rev is None or rev.stamp_id != stamp_id:
        abort(404)
    return jsonify(rev.to_dict(include_svg=True))


@tsd_stamps_api.route("/usage-analytics", methods=["GET"])
@login_required
def usage_analytics():
    """Aggregate stamp-application analytics for the tenant.

    Query params:
      - days=N (default 30): lookback window.
      - top=N (default 5):    how many top stamps/users to return.
    """
    from datetime import datetime, timedelta
    actor = _actor()
    try:
        days = max(1, min(365, int(request.args.get("days", 30))))
        top = max(1, min(20, int(request.args.get("top", 5))))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_params"}), 400

    since = datetime.utcnow() - timedelta(days=days)
    base_q = TSDStampInsertion.query.filter(
        TSDStampInsertion.organization_id == actor.organization_id,
        TSDStampInsertion.placed_at >= since,
    )
    total = base_q.count()
    revoked_count = base_q.filter(TSDStampInsertion.revoked_at.isnot(None)).count()
    active_count = total - revoked_count

    # --- Top stamps (by insertion count) ---
    from sqlalchemy import func as _func
    top_stamps_rows = (
        db.session.query(
            TSDStampInsertion.stamp_id,
            _func.count(TSDStampInsertion.id).label("n"),
        )
        .filter(TSDStampInsertion.organization_id == actor.organization_id,
                TSDStampInsertion.placed_at >= since)
        .group_by(TSDStampInsertion.stamp_id)
        .order_by(_func.count(TSDStampInsertion.id).desc())
        .limit(top).all()
    )
    name_by_id = dict(
        db.session.query(TSDStamp.id, TSDStamp.name)
        .filter(TSDStamp.id.in_([r[0] for r in top_stamps_rows] or [-1]))
        .all()
    )
    top_stamps = [
        {"stamp_id": sid, "name": name_by_id.get(sid, f"#{sid}"), "count": n}
        for sid, n in top_stamps_rows
    ]

    # --- Top users (by applications) ---
    top_users_rows = (
        db.session.query(
            TSDStampInsertion.placed_by_id,
            _func.count(TSDStampInsertion.id).label("n"),
        )
        .filter(TSDStampInsertion.organization_id == actor.organization_id,
                TSDStampInsertion.placed_at >= since)
        .group_by(TSDStampInsertion.placed_by_id)
        .order_by(_func.count(TSDStampInsertion.id).desc())
        .limit(top).all()
    )
    users_by_id = {
        u.id: u
        for u in User.query.filter(User.id.in_([r[0] for r in top_users_rows] or [-1])).all()
    }
    top_users = [
        {
            "user_id": uid,
            "name": _user_display(users_by_id.get(uid), uid)["name"],
            "email": _user_display(users_by_id.get(uid), uid)["email"],
            "count": n,
        }
        for uid, n in top_users_rows
    ]

    # --- Unique counts & channel breakdown ---
    unique_stamps_used = db.session.query(_func.count(_func.distinct(TSDStampInsertion.stamp_id))).filter(
        TSDStampInsertion.organization_id == actor.organization_id,
        TSDStampInsertion.placed_at >= since,
    ).scalar() or 0
    unique_users = db.session.query(_func.count(_func.distinct(TSDStampInsertion.placed_by_id))).filter(
        TSDStampInsertion.organization_id == actor.organization_id,
        TSDStampInsertion.placed_at >= since,
    ).scalar() or 0
    unique_documents = db.session.query(_func.count(_func.distinct(TSDStampInsertion.document_id))).filter(
        TSDStampInsertion.organization_id == actor.organization_id,
        TSDStampInsertion.placed_at >= since,
        TSDStampInsertion.document_id.isnot(None),
    ).scalar() or 0

    channel_breakdown = {"tsd_document": 0, "svg_export": 0, "png_export": 0, "pdf_export": 0}
    for ctx_lbl, doc_id in (
        db.session.query(TSDStampInsertion.context_label, TSDStampInsertion.document_id)
        .filter(
            TSDStampInsertion.organization_id == actor.organization_id,
            TSDStampInsertion.placed_at >= since,
        )
        .all()
    ):
        ch = _infer_channel(ctx_lbl, doc_id)
        channel_breakdown[ch] = channel_breakdown.get(ch, 0) + 1

    # --- Daily bucket counts ---
    daily_rows = (
        db.session.query(
            _func.date(TSDStampInsertion.placed_at).label("d"),
            _func.count(TSDStampInsertion.id).label("n"),
        )
        .filter(TSDStampInsertion.organization_id == actor.organization_id,
                TSDStampInsertion.placed_at >= since)
        .group_by("d")
        .order_by("d")
        .all()
    )
    daily = [{"date": str(d), "count": n} for d, n in daily_rows]

    return jsonify({
        "days": days,
        "since": since.isoformat(),
        "total_insertions": total,
        "active_insertions": active_count,
        "revoked_insertions": revoked_count,
        "unique_stamps_used": unique_stamps_used,
        "unique_users": unique_users,
        "unique_documents": unique_documents,
        "channel_breakdown": channel_breakdown,
        "top_stamps": top_stamps,
        "top_users": top_users,
        "daily": daily,
    })


@tsd_stamps_api.route("/<int:stamp_id>/audit", methods=["GET"])
@login_required
def stamp_audit(stamp_id: int):
    actor = _actor()
    _owned_stamp(stamp_id, actor)
    events = (
        SecurityEvent.query
        .filter(SecurityEvent.organization_id == actor.organization_id,
                SecurityEvent.resource_type == "tsd_stamp",
                SecurityEvent.resource_id == stamp_id)
        .order_by(SecurityEvent.created_at.desc())
        .limit(200)
        .all()
    )
    u_ids = {e.actor_id for e in events if e.actor_id}
    users = {
        u.id: u
        for u in User.query.filter(User.id.in_(list(u_ids) or [-1])).all()
    }
    return jsonify({
        "stamp_id": stamp_id,
        "count": len(events),
        "events": [{
            "action": e.action,
            "outcome": e.outcome,
            "actor_id": e.actor_id,
            "actor_name": _user_display(users.get(e.actor_id), e.actor_id)["name"],
            "actor_email": _user_display(users.get(e.actor_id), e.actor_id)["email"],
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "correlation_id": e.correlation_id,
        } for e in events],
    })
