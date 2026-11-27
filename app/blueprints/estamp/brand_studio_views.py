"""Web views for TRUSTSEAL Brand Identity Studio & Printable Brand Guidelines Book."""
from __future__ import annotations

from flask import Blueprint, abort, render_template
from flask_login import current_user, login_required

from app.models.brand_identity import BrandIdentityKit, ensure_brand_studio_tables
from app.services.brand_studio_engine import (
    BRAND_ICONS,
    BRAND_PALETTES,
    FONT_PAIRINGS,
    INDUSTRIES,
    MOCKUP_CATALOG,
    build_brand_guidelines,
)

brand_studio_views = Blueprint(
    "brand_studio_views",
    __name__,
    url_prefix="/brand-studio",
    template_folder="../../templates",
)


@brand_studio_views.route("", methods=["GET"])
@brand_studio_views.route("/", methods=["GET"])
@login_required
def studio_page():
    ensure_brand_studio_tables()
    org_name = (current_user.organization.name if current_user.organization else "TRUSTSEAL Enterprise")
    kits = (
        BrandIdentityKit.query.filter_by(organization_id=current_user.organization_id, is_active=True)
        .order_by(BrandIdentityKit.updated_at.desc())
        .all()
    )
    return render_template(
        "stamps/brand_studio.html",
        active_nav_item="brand-studio",
        default_brand_name=org_name,
        icons=BRAND_ICONS,
        palettes=BRAND_PALETTES,
        fonts=FONT_PAIRINGS,
        industries=INDUSTRIES,
        mockups=MOCKUP_CATALOG,
        saved_kits=kits,
    )


@brand_studio_views.route("/guidelines/<int:kit_id>", methods=["GET"])
@login_required
def guidelines_print_page(kit_id: int):
    ensure_brand_studio_tables()
    kit = BrandIdentityKit.query.filter_by(
        id=kit_id, organization_id=current_user.organization_id, is_active=True
    ).first()
    if not kit:
        abort(404)
    guidelines = kit.guidelines_json or build_brand_guidelines(kit.to_dict(include_svgs=False))
    return render_template(
        "stamps/brand_guidelines_print.html",
        kit=kit,
        guidelines=guidelines,
    )


@brand_studio_views.route("/business-cards/<int:kit_id>", methods=["GET"])
@login_required
def business_cards_print_page(kit_id: int):
    ensure_brand_studio_tables()
    kit = BrandIdentityKit.query.filter_by(
        id=kit_id, organization_id=current_user.organization_id, is_active=True
    ).first()
    if not kit:
        abort(404)
    return render_template(
        "stamps/brand_business_cards.html",
        kit=kit,
        icons=BRAND_ICONS,
        current_user=current_user,
    )
