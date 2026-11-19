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
from app.models.tsd_stamp import TSD_STAMP_KINDS, TSDStamp
from app.models.tsd_stamp_insertion import TSDStampInsertion
from app.models.tsd_stamp_revision import TSDStampRevision
from app.services import tsd_stamp_templates
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
        action=action,
        resource_type="tsd_stamp",
        resource_id=resource_id,
        outcome=outcome,
        correlation_id=correlation_id or uuid.uuid4().hex,
    ))


def _validate_svg(s: str, field: str = "svg") -> None:
    s = (s or "").strip()
    if not s.startswith("<svg") or not s.endswith("</svg>"):
        abort(400, description=f"{field}_invalid")
    if len(s) > 512 * 1024:
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


# ============================================================ receipts


@tsd_stamps_api.route("/<int:stamp_id>/receipt", methods=["POST"])
@login_required
def mint_receipt(stamp_id: int):
    actor = _actor()
    row = _owned_stamp(stamp_id, actor)
    payload = request.get_json(silent=True) or {}

    svg = (payload.get("svg") or row.svg or "").strip()
    _validate_svg(svg, field="context_svg")
    svg = canonicalize_inserted_svg(svg)

    document_id = payload.get("document_id")
    if document_id is not None:
        try:
            document_id = int(document_id)
        except (TypeError, ValueError):
            return jsonify({"error": "document_id_invalid"}), 400
    context_label = (payload.get("context_label") or "").strip() or None

    receipt = issue_receipt(
        organization_id=actor.organization_id,
        stamp=row,
        placed_by_id=actor.id,
        document_id=document_id,
        context_label=context_label,
        context_svg=svg,
    )
    _emit("tsd.stamp_insert", row.id, outcome=f"receipt:{receipt.id}")
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
        "verify_url": verify_url,
        "qr_url": qr_url,
    }), 201


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

    if context_svg:
        context_svg = canonicalize_inserted_svg(context_svg)

    result = verify_receipt(
        organization_id=actor.organization_id,
        receipt_id=receipt_id,
        nonce=str(nonce),
        context_svg=context_svg,
    )
    return jsonify(result)


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
    return jsonify({
        "stamp_id": stamp_id,
        "count": len(rows),
        "insertions": [r.to_dict() for r in rows],
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

    svg_bytes = BytesIO(svg_src.encode("utf-8"))
    try:
        drawing = svg2rlg(svg_bytes)
    except Exception as e:
        return jsonify({"error": "svg_parse_failed", "detail": str(e)}), 500

    page_w = w_mm * mm
    page_h = h_mm * mm
    scale_x = page_w / drawing.width  if drawing.width  else 1
    scale_y = page_h / drawing.height if drawing.height else 1
    if mirror:
        # Flip horizontally and translate back into bounds.
        drawing.translate(drawing.width, 0)
        drawing.scale(-scale_x, scale_y)
    else:
        drawing.scale(scale_x, scale_y)
    drawing.width, drawing.height = page_w, page_h

    buf = BytesIO()
    c = _pdfcanvas.Canvas(buf, pagesize=(page_w, page_h))
    renderPDF.draw(drawing, c, 0, 0)
    c.showPage()
    c.save()
    buf.seek(0)

    from flask import send_file
    # Name the file descriptively so a user export doesn't overwrite a plate.
    suffix = []
    if zone: suffix.append("zone-" + zone.lstrip("#"))
    if mirror: suffix.append("mirror")
    if polarity == "negative": suffix.append("neg")
    if grayscale: suffix.append("gray")
    tag = ("_" + "_".join(suffix)) if suffix else ""
    return send_file(buf, mimetype="application/pdf",
                     as_attachment=True,
                     download_name=f"{row.name}{tag}.pdf")


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
    top_users = [{"user_id": uid, "count": n} for uid, n in top_users_rows]

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
    return jsonify({
        "stamp_id": stamp_id,
        "count": len(events),
        "events": [{
            "action": e.action,
            "outcome": e.outcome,
            "actor_id": e.actor_id,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "correlation_id": e.correlation_id,
        } for e in events],
    })
