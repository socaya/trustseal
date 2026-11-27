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
