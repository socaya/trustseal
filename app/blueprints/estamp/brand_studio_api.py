"""REST API for TRUSTSEAL Brand Identity Studio.

Supports Smashing-Logo-style concept generation, parametric SVG rendering,
Brand Identity Kit persistence, vector SVG / Brand Book exports, and one-click
publishing directly to TRUSTSEAL Media Library.
"""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime

from flask import Blueprint, Response, jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from flask_login import current_user

from app.extensions import db
from app.models.brand_identity import BrandIdentityKit, ensure_brand_studio_tables
from app.models.media_asset import MediaAsset
from app.models.tsd_letterhead import TSDLetterhead, render_letterhead_parts
from app.models.tsd_stamp import TSDStamp
from app.models.user import User
from app.services.brand_studio_engine import (
    BRAND_ICONS,
    BRAND_PALETTES,
    FONT_PAIRINGS,
    INDUSTRIES,
    MOCKUP_CATALOG,
    build_brand_guidelines,
    generate_logo_concepts,
    render_logo_variants,
    sanitize_hex,
)
from app.services.tsd_stamp_templates import (
    _company_dated_svg,
    _company_rect_svg,
    _seal_svg,
)

brand_studio_api = Blueprint("brand_studio_api", __name__, url_prefix="/api/brand-studio")


def _resolve_actor() -> User | None:
    if current_user and getattr(current_user, "is_authenticated", False):
        return current_user
    try:
        verify_jwt_in_request(optional=True)
        uid = get_jwt_identity()
        if uid is not None:
            u = db.session.get(User, int(uid))
            if u and u.is_active:
                return u
    except Exception:
        pass
    return None


def _require_actor():
    u = _resolve_actor()
    if u is None or not u.organization_id:
        return None, (jsonify(error="Authentication required"), 401)
    ensure_brand_studio_tables()
    return u, None


@brand_studio_api.route("/catalog", methods=["GET"])
def get_brand_catalog():
    return jsonify(
        icons=BRAND_ICONS,
        palettes=BRAND_PALETTES,
        fonts=FONT_PAIRINGS,
        industries=INDUSTRIES,
        mockups=MOCKUP_CATALOG,
    ), 200


@brand_studio_api.route("/generate", methods=["POST"])
def generate_concepts():
    actor, err = _require_actor()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    brand_name = (data.get("brand_name") or "").strip()
    if not brand_name:
        return jsonify(error="brand_name is required"), 400
    concepts = generate_logo_concepts(
        brand_name=brand_name,
        tagline=(data.get("tagline") or "").strip(),
        industry=(data.get("industry") or "Technology & SaaS").strip(),
        archetype=(data.get("archetype") or "modern_corporate").strip(),
        count=int(data.get("count") or 12),
    )
    return jsonify(brand_name=brand_name, count=len(concepts), concepts=concepts), 200


@brand_studio_api.route("/preview", methods=["POST"])
def preview_identity():
    actor, err = _require_actor()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    svgs = render_logo_variants(data)
    guidelines = build_brand_guidelines(data)
    return jsonify(**svgs, guidelines=guidelines), 200


@brand_studio_api.route("/kits", methods=["GET", "POST"])
def kits_collection():
    actor, err = _require_actor()
    if err:
        return err

    if request.method == "GET":
        rows = (
            BrandIdentityKit.query.filter_by(organization_id=actor.organization_id, is_active=True)
            .order_by(BrandIdentityKit.updated_at.desc())
            .all()
        )
        return jsonify(kits=[r.to_dict(include_svgs=True) for r in rows]), 200

    data = request.get_json(silent=True) or {}
    brand_name = (data.get("brand_name") or "").strip()
    if not brand_name:
        return jsonify(error="brand_name is required"), 400

    params = {
        "brand_name": brand_name,
        "tagline": (data.get("tagline") or "").strip(),
        "industry": (data.get("industry") or "Technology & SaaS").strip(),
        "archetype": (data.get("archetype") or "modern_corporate").strip(),
        "icon_id": (data.get("icon_id") or "shield_check").strip(),
        "logo_layout": (data.get("logo_layout") or "horizontal").strip(),
        "font_heading": (data.get("font_heading") or "Inter, -apple-system, sans-serif").strip(),
        "font_body": (data.get("font_body") or "Inter, -apple-system, sans-serif").strip(),
        "letter_spacing": float(data.get("letter_spacing", 1.5)),
        "icon_scale": float(data.get("icon_scale", 1.0)),
        "primary_color": sanitize_hex(data.get("primary_color") or "#002769"),
        "secondary_color": sanitize_hex(data.get("secondary_color") or "#02982e"),
        "accent_color": sanitize_hex(data.get("accent_color") or "#1d4ed8"),
        "dark_color": sanitize_hex(data.get("dark_color") or "#0f172a"),
        "light_color": sanitize_hex(data.get("light_color") or "#f4f7fc"),
    }
    svgs = render_logo_variants(params)
    guidelines = build_brand_guidelines(params)

    kit = BrandIdentityKit(
        organization_id=actor.organization_id,
        created_by_id=actor.id,
        kit_ref=BrandIdentityKit.generate_ref(actor.organization_id),
        **params,
        **svgs,
        guidelines_json=guidelines,
    )
    db.session.add(kit)
    db.session.commit()
    return jsonify(kit=kit.to_dict(include_svgs=True)), 201


@brand_studio_api.route("/kits/<int:kit_id>", methods=["GET", "PATCH", "DELETE"])
def kit_item(kit_id: int):
    actor, err = _require_actor()
    if err:
        return err
    kit = BrandIdentityKit.query.filter_by(id=kit_id, organization_id=actor.organization_id, is_active=True).first()
    if not kit:
        return jsonify(error="Brand Identity Kit not found"), 404

    if request.method == "GET":
        return jsonify(kit=kit.to_dict(include_svgs=True)), 200

    if request.method == "DELETE":
        kit.is_active = False
        db.session.commit()
        return jsonify(deleted=True, id=kit_id), 200

    data = request.get_json(silent=True) or {}
    for field in ("brand_name", "tagline", "industry", "archetype", "icon_id", "logo_layout", "font_heading", "font_body"):
        if field in data and data[field] is not None:
            setattr(kit, field, str(data[field]).strip())
    for cfield in ("primary_color", "secondary_color", "accent_color", "dark_color", "light_color"):
        if cfield in data and data[cfield]:
            setattr(kit, cfield, sanitize_hex(str(data[cfield])))
    if "letter_spacing" in data:
        kit.letter_spacing = float(data["letter_spacing"])
    if "icon_scale" in data:
        kit.icon_scale = float(data["icon_scale"])

    params = kit.to_dict(include_svgs=False)
    svgs = render_logo_variants(params)
    kit.primary_svg = svgs["primary_svg"]
    kit.mono_dark_svg = svgs["mono_dark_svg"]
    kit.mono_light_svg = svgs["mono_light_svg"]
    kit.icon_only_svg = svgs["icon_only_svg"]
    kit.guidelines_json = build_brand_guidelines(params)
    kit.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(kit=kit.to_dict(include_svgs=True)), 200


@brand_studio_api.route("/kits/<int:kit_id>/export/<variant>", methods=["GET"])
def export_kit_asset(kit_id: int, variant: str):
    actor, err = _require_actor()
    if err:
        return err
    kit = BrandIdentityKit.query.filter_by(id=kit_id, organization_id=actor.organization_id, is_active=True).first()
    if not kit:
        return jsonify(error="Brand Identity Kit not found"), 404

    if variant == "guidelines":
        return jsonify(kit_ref=kit.kit_ref, guidelines=kit.guidelines_json or build_brand_guidelines(kit.to_dict(include_svgs=False))), 200

    mapping = {
        "primary": kit.primary_svg,
        "mono-dark": kit.mono_dark_svg,
        "mono-light": kit.mono_light_svg,
        "icon": kit.icon_only_svg,
    }
    svg = mapping.get(variant)
    if not svg:
        return jsonify(error="Unknown export variant (use primary, mono-dark, mono-light, icon, guidelines)"), 400
    fname = f"{kit.kit_ref.lower()}-{variant}.svg"
    return Response(
        svg,
        mimetype="image/svg+xml",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@brand_studio_api.route("/kits/<int:kit_id>/publish-media", methods=["POST"])
def publish_kit_to_media(kit_id: int):
    """Publish a Brand Identity Kit's primary vector logo directly into TRUSTSEAL Media Library."""
    actor, err = _require_actor()
    if err:
        return err
    kit = BrandIdentityKit.query.filter_by(id=kit_id, organization_id=actor.organization_id, is_active=True).first()
    if not kit:
        return jsonify(error="Brand Identity Kit not found"), 404

    data = request.get_json(silent=True) or {}
    variant = (data.get("variant") or "primary").strip()
    svg = {
        "primary": kit.primary_svg,
        "mono-dark": kit.mono_dark_svg,
        "mono-light": kit.mono_light_svg,
        "icon": kit.icon_only_svg,
    }.get(variant) or kit.primary_svg

    raw_bytes = svg.encode("utf-8")
    b64 = base64.b64encode(raw_bytes).decode("ascii")
    data_uri = f"data:image/svg+xml;base64,{b64}"
    sha = hashlib.sha256(raw_bytes).hexdigest()

    asset = MediaAsset(
        organization_id=actor.organization_id,
        uploaded_by_id=actor.id,
        name=f"{kit.brand_name} — {variant.replace('-', ' ').title()} Logo ({kit.kit_ref})",
        category="logo",
        mime_type="image/svg+xml",
        data_uri=data_uri,
        width=480,
        height=120,
        size_bytes=len(raw_bytes),
        sha256=sha,
    )
    db.session.add(asset)
    db.session.flush()
    kit.media_asset_id = asset.id
    db.session.commit()
    return jsonify(published=True, media_asset=asset.to_dict(include_data=False), kit=kit.to_dict(include_svgs=False)), 201


def _svg_to_data_uri(svg: str) -> str:
    clean = (svg or "").strip()
    if 'viewBox="0 0 96 96"' in clean and 'width="' not in clean:
        clean = clean.replace('viewBox="0 0 96 96"', 'viewBox="0 0 96 96" width="96" height="96"', 1)
    raw = clean.encode("utf-8")
    return "data:image/svg+xml;base64," + base64.b64encode(raw).decode("ascii")


def _font_style_for_letterhead(font_heading: str) -> str:
    fh = (font_heading or "").lower()
    if "georgia" in fh or "palatino" in fh or "serif" in fh:
        return "serif"
    if "helvetica" in fh:
        return "modern"
    return "sans"


def _unique_stamp_name(org_id: int, base_name: str) -> str:
    candidate = base_name.strip()[:112]
    existing = {
        row[0]
        for row in db.session.query(TSDStamp.name).filter_by(organization_id=org_id).all()
    }
    if candidate not in existing:
        return candidate
    idx = 2
    while f"{candidate} ({idx})" in existing:
        idx += 1
    return f"{candidate} ({idx})"[:120]


def _build_letterhead_from_kit(kit: BrandIdentityKit, actor: User, opts: dict | None = None) -> TSDLetterhead:
    opts = opts or {}
    style = (opts.get("style") or "executive_split").strip().lower()
    logo_uri = _svg_to_data_uri(kit.icon_only_svg or kit.primary_svg)
    slug_domain = "".join(ch for ch in (kit.brand_name or "brand").lower() if ch.isalnum()) or "brand"

    align = "split"
    bg_pattern = "geometric_corners"
    divider_style = "solid"
    top_bar_px = 6
    if style == "ceremonial_crest":
        align = "center"
        bg_pattern = "certificate_frame"
        divider_style = "double"
        top_bar_px = 0
    elif style == "side_ribbon":
        align = "left"
        bg_pattern = "side_accent_ribbon"
        divider_style = "solid"
        top_bar_px = 5

    layout = {
        "header_align": align,
        "accent_color": kit.primary_color,
        "brand_secondary": kit.secondary_color,
        "secondary_color": kit.dark_color,
        "font_style": _font_style_for_letterhead(kit.font_heading),
        "top_bar_px": top_bar_px,
        "divider_style": divider_style,
        "show_divider": True,
        "show_ref_bar": True,
        "show_trust_badge": True,
        "show_footer_rule": True,
        "show_bottom_bar": True,
        "paper_size": "a4",
        "orientation": "portrait",
        "margin_mm": 22,
        "bg_pattern": bg_pattern,
        "bg_pattern_opacity": 80,
        "paper_bg": "#ffffff",
        "logo_data_uri": logo_uri,
        "logo_height_px": 56,
        "logo_width_px": 160,
        "org_name": (kit.brand_name or "").upper(),
        "org_uppercase": True,
        "tagline": kit.tagline or "Verified Integrity",
        "address": (opts.get("address") or "Corporate Headquarters · Executive Suite").strip(),
        "phone": (opts.get("phone") or "+1 (800) 555-0194").strip(),
        "email": (opts.get("email") or f"office@{slug_domain}.com").strip(),
        "website": (opts.get("website") or f"www.{slug_domain}.com").strip(),
        "reg_no": (opts.get("reg_no") or f"BRAND REF: {kit.kit_ref}").strip(),
        "footer_text": (opts.get("footer_text") or f"{kit.brand_name} · Official Corporate Stationery · {kit.kit_ref}").strip(),
        "brand_kit_id": kit.id,
        "brand_kit_ref": kit.kit_ref,
    }
    header_html, footer_html = render_letterhead_parts(layout)
    lh_name = (opts.get("name") or f"{kit.brand_name} — Official Brand Letterhead").strip()[:140]
    lh = TSDLetterhead(
        organization_id=actor.organization_id,
        created_by_id=actor.id,
        name=lh_name,
        description=f"Generated from Brand Identity Studio ({kit.kit_ref})",
        is_default=bool(opts.get("is_default", False)),
        status="active",
        layout=layout,
        header_html=header_html,
        footer_html=footer_html,
    )
    db.session.add(lh)
    db.session.flush()
    return lh


def _build_stamp_from_kit(kit: BrandIdentityKit, actor: User, opts: dict | None = None) -> TSDStamp:
    opts = opts or {}
    stamp_kind = (opts.get("kind") or "seal").strip().lower()
    if stamp_kind not in ("seal", "company_dated", "company_rect"):
        stamp_kind = "seal"

    color = sanitize_hex(opts.get("color") or kit.primary_color, "#002769")
    logo_uri = _svg_to_data_uri(kit.icon_only_svg or kit.primary_svg)
    company = (kit.brand_name or "TRUSTSEAL").strip().upper()
    tagline = (kit.tagline or "OFFICIAL CORPORATE SEAL").strip().upper()
    center_word = (opts.get("center_text") or "OFFICIAL SEAL").strip().upper()

    if stamp_kind == "company_dated":
        verb = (opts.get("verb") or "APPROVED").strip().upper()
        svg = _company_dated_svg(
            company=company,
            tagline=tagline,
            verb=verb,
            color=color,
            logo_url=logo_uri,
        )
        layout = {
            "company": company,
            "tagline": tagline,
            "verb": verb,
            "date_format": "DD MMM YYYY",
            "color": color,
            "border_style": "double",
            "shape": "circle",
            "width_mm": 42,
            "height_mm": 42,
            "size_value": "42",
            "logo_data_uri": logo_uri,
            "logo_x": 50,
            "logo_y": 35,
            "logo_size": 20,
            "logo_style": "original",
            "logo_auto_match_color": False,
            "description": f"Dated Brand Stamp generated from {kit.kit_ref}",
            "brand_kit_id": kit.id,
            "brand_kit_ref": kit.kit_ref,
        }
        default_name = f"{kit.brand_name} — Dated Corporate Seal"
    elif stamp_kind == "company_rect":
        slug_domain = "".join(ch for ch in (kit.brand_name or "brand").lower() if ch.isalnum()) or "brand"
        svg = _company_rect_svg(
            company=company,
            subtitle=tagline,
            department=(opts.get("department") or "EXECUTIVE OFFICE").strip().upper(),
            address1=(opts.get("address") or "Corporate Headquarters").strip(),
            reg_line=f"REF: {kit.kit_ref}",
            contact=f"www.{slug_domain}.com",
            color=color,
            border_style="double",
            header_bar=True,
            logo_url=logo_uri,
        )
        layout = {
            "company": company,
            "subtitle": tagline,
            "department": (opts.get("department") or "EXECUTIVE OFFICE").strip().upper(),
            "address1": (opts.get("address") or "Corporate Headquarters").strip(),
            "reg_line": f"REF: {kit.kit_ref}",
            "contact": f"www.{slug_domain}.com",
            "color": color,
            "border_style": "double",
            "header_bar": True,
            "width_mm": 75,
            "height_mm": 38,
            "size_value": "75x38",
            "logo_data_uri": logo_uri,
            "description": f"Rectangular Brand Stamp generated from {kit.kit_ref}",
            "brand_kit_id": kit.id,
            "brand_kit_ref": kit.kit_ref,
        }
        default_name = f"{kit.brand_name} — Corporate Registry Stamp"
    else:
        center_lines = [ln.strip() for ln in center_word.splitlines() if ln.strip()] or ["OFFICIAL SEAL"]
        svg = _seal_svg(
            top=company,
            bottom=tagline,
            center_lines=center_lines,
            color=color,
            border="double",
            logo_url=logo_uri,
            logo_size=62,
        )
        top_fs = 13 if len(company) > 20 else (15 if len(company) > 15 else 18)
        bot_fs = 13 if len(tagline) > 20 else (15 if len(tagline) > 15 else 17)
        layout = {
            "top": company,
            "bottom": tagline,
            "center": center_lines,
            "size_top": top_fs,
            "size_bottom": bot_fs,
            "color": color,
            "border_style": "double",
            "shape": "circle",
            "width_mm": 42,
            "height_mm": 42,
            "size_value": "42",
            "logo_data_uri": logo_uri,
            "logo_x": 50,
            "logo_y": 38,
            "logo_size": 22,
            "logo_style": "original",
            "logo_auto_match_color": False,
            "description": f"Official Brand Seal generated from {kit.kit_ref}",
            "brand_kit_id": kit.id,
            "brand_kit_ref": kit.kit_ref,
        }
        default_name = f"{kit.brand_name} — Official Corporate Seal"

    stamp_name = _unique_stamp_name(actor.organization_id, opts.get("name") or default_name)
    st = TSDStamp(
        organization_id=actor.organization_id,
        created_by_id=actor.id,
        name=stamp_name,
        kind=stamp_kind,
        layout=layout,
        svg=svg,
        status="draft",
    )
    db.session.add(st)
    db.session.flush()
    return st


@brand_studio_api.route("/kits/<int:kit_id>/create-letterhead", methods=["POST"])
def create_letterhead_from_kit(kit_id: int):
    """Create a live TSDLetterhead pre-styled with this Brand Identity Kit."""
    actor, err = _require_actor()
    if err:
        return err
    kit = BrandIdentityKit.query.filter_by(id=kit_id, organization_id=actor.organization_id, is_active=True).first()
    if not kit:
        return jsonify(error="Brand Identity Kit not found"), 404
    opts = request.get_json(silent=True) or {}
    lh = _build_letterhead_from_kit(kit, actor, opts)
    db.session.commit()
    return jsonify(
        created=True,
        letterhead=lh.to_dict(),
        edit_url=f"/letterheads?id={lh.id}",
    ), 201


@brand_studio_api.route("/kits/<int:kit_id>/create-stamp", methods=["POST"])
def create_stamp_from_kit(kit_id: int):
    """Create a live TSDStamp (round seal, dated seal, or rectangular stamp) from this Brand Identity Kit."""
    actor, err = _require_actor()
    if err:
        return err
    kit = BrandIdentityKit.query.filter_by(id=kit_id, organization_id=actor.organization_id, is_active=True).first()
    if not kit:
        return jsonify(error="Brand Identity Kit not found"), 404
    opts = request.get_json(silent=True) or {}
    st = _build_stamp_from_kit(kit, actor, opts)
    db.session.commit()
    return jsonify(
        created=True,
        stamp=st.to_dict(include_svg=True),
        edit_url=f"/stamps/studio/{st.id}",
    ), 201


@brand_studio_api.route("/kits/<int:kit_id>/deploy-brand-suite", methods=["POST"])
def deploy_full_brand_suite(kit_id: int):
    """One-click executive deployment: Media Library Logo + Official Letterhead + Corporate Seals + Business Cards."""
    actor, err = _require_actor()
    if err:
        return err
    kit = BrandIdentityKit.query.filter_by(id=kit_id, organization_id=actor.organization_id, is_active=True).first()
    if not kit:
        return jsonify(error="Brand Identity Kit not found"), 404

    opts = request.get_json(silent=True) or {}

    # 1. Publish Primary & Icon SVG to Media Library
    published_assets = []
    for variant, svg in (("primary", kit.primary_svg), ("icon", kit.icon_only_svg)):
        raw_bytes = (svg or "").encode("utf-8")
        asset = MediaAsset(
            organization_id=actor.organization_id,
            uploaded_by_id=actor.id,
            name=f"{kit.brand_name} — {variant.title()} Logo ({kit.kit_ref})",
            category="logo",
            mime_type="image/svg+xml",
            data_uri="data:image/svg+xml;base64," + base64.b64encode(raw_bytes).decode("ascii"),
            width=480 if variant == "primary" else 96,
            height=120 if variant == "primary" else 96,
            size_bytes=len(raw_bytes),
            sha256=hashlib.sha256(raw_bytes).hexdigest(),
        )
        db.session.add(asset)
        db.session.flush()
        published_assets.append(asset.to_dict(include_data=False))
        if variant == "primary":
            kit.media_asset_id = asset.id

    # 2. Create Official Brand Letterhead
    lh = _build_letterhead_from_kit(kit, actor, opts.get("letterhead") or opts)

    # 3. Create Official Round Corporate Seal + Dated Approval Stamp
    seal = _build_stamp_from_kit(kit, actor, {"kind": "seal", "center_text": "OFFICIAL SEAL"})
    dated = _build_stamp_from_kit(kit, actor, {"kind": "company_dated", "verb": "APPROVED"})

    db.session.commit()
    return jsonify(
        deployed=True,
        kit_ref=kit.kit_ref,
        media_assets=published_assets,
        letterhead=lh.to_dict(),
        stamp_seal=seal.to_dict(include_svg=False),
        stamp_dated=dated.to_dict(include_svg=False),
        links={
            "letterhead_url": f"/letterheads?id={lh.id}",
            "stamp_seal_url": f"/stamps/studio/{seal.id}",
            "stamp_dated_url": f"/stamps/studio/{dated.id}",
            "business_cards_url": f"/brand-studio/business-cards/{kit.id}",
            "guidelines_url": f"/brand-studio/guidelines/{kit.id}",
            "media_url": "/media",
        },
    ), 201
