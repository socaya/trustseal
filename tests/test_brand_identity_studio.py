"""End-to-end tests for TRUSTSEAL Brand Identity Studio.

Covers:
- Parametric SVG engine (24 icons, 12 palettes, 4 production variants, HEX->RGB/CMYK)
- Smashing-Logo-style 12-concept generator
- Authenticated REST API (/api/brand-studio/*) CRUD, SVG export, and Media Library publishing
- Brand Studio web view (/brand-studio), Printable Brand Guidelines Book (/brand-studio/guidelines/<id>),
  and public module showcase (/platform/brand-studio)
"""
from __future__ import annotations

import pytest

from app.extensions import db
from app.models.media_asset import MediaAsset
from app.models.organization import Organization
from app.models.user import User
from app.services.brand_studio_engine import (
    BRAND_ICONS,
    BRAND_PALETTES,
    MOCKUP_CATALOG,
    build_brand_guidelines,
    generate_logo_concepts,
    hex_to_cmyk,
    hex_to_rgb,
    render_logo_variants,
)


def _create_logged_in_client(pg_app):
    with pg_app.app_context():
        org = Organization(name="Apex Sovereign Holdings")
        db.session.add(org)
        db.session.flush()
        user = User(
            email="brand.director@apex.test",
            username="brand_director",
            first_name="Elena",
            last_name="Vance",
            organization_id=org.id,
            is_active=True,
        )
        user.set_password("BrandStudio#2026!")
        db.session.add(user)
        db.session.commit()
        uid = user.id
        oid = org.id

    client = pg_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(uid)
        sess["_fresh"] = True
    return client, uid, oid


def test_engine_catalog_and_color_math():
    assert len(BRAND_ICONS) == 24
    assert len(BRAND_PALETTES) == 12
    assert len(MOCKUP_CATALOG) == 10
    assert hex_to_rgb("#002769") == (0, 39, 105)
    c, m, y, k = hex_to_cmyk("#002769")
    assert c == 100 and k > 50

    variants = render_logo_variants({
        "brand_name": "Meridian Capital",
        "tagline": "Verified Trust",
        "icon_id": "shield_check",
        "logo_layout": "horizontal",
        "primary_color": "#002769",
        "secondary_color": "#02982e",
    })
    for key in ("primary_svg", "mono_dark_svg", "mono_light_svg", "icon_only_svg"):
        assert "<svg" in variants[key]
        assert "</svg>" in variants[key]

    concepts = generate_logo_concepts(
        brand_name="Meridian Capital",
        tagline="Global Advisory",
        industry="Finance, Banking & SACCO",
        count=12,
    )
    assert len(concepts) == 12
    assert len({c["icon_id"] for c in concepts}) >= 6

    book = build_brand_guidelines({"brand_name": "Meridian Capital", "primary_color": "#002769"})
    assert len(book["colors"]) == 5
    assert book["colors"][0]["hex"] == "#002769"
    assert len(book["dos"]) >= 4 and len(book["donts"]) >= 4


def test_brand_studio_api_and_views_end_to_end(pg_app):
    client, _uid, oid = _create_logged_in_client(pg_app)
    hdrs = {"X-Requested-With": "fetch"}

    # 1. Public showcase page
    pub = client.get("/platform/brand-studio")
    assert pub.status_code == 200
    assert b"Brand Identity Studio" in pub.data

    # 2. Studio main view
    studio = client.get("/brand-studio")
    assert studio.status_code == 200
    assert b"Brand Identity Studio" in studio.data
    assert b"Branded Merchandise" in studio.data

    # 3. Catalog endpoint
    cat = client.get("/api/brand-studio/catalog", headers=hdrs)
    assert cat.status_code == 200
    cdata = cat.get_json()
    assert len(cdata["icons"]) == 24
    assert len(cdata["mockups"]) == 10

    # 4. Concept Generator (12 Smashing-Logo concepts)
    gen = client.post(
        "/api/brand-studio/generate",
        headers=hdrs,
        json={
            "brand_name": "Vanguard Logistics",
            "tagline": "Precision Fleet Mobility",
            "industry": "Logistics, Fleet & Trade",
            "count": 12,
        },
    )
    assert gen.status_code == 200
    gdata = gen.get_json()
    assert gdata["count"] == 12
    assert len(gdata["concepts"]) == 12
    first = gdata["concepts"][0]

    # 5. Create Brand Identity Kit
    created = client.post(
        "/api/brand-studio/kits",
        headers=hdrs,
        json={
            "brand_name": first["brand_name"],
            "tagline": first["tagline"],
            "industry": first["industry"],
            "icon_id": first["icon_id"],
            "logo_layout": first["logo_layout"],
            "primary_color": first["primary_color"],
            "secondary_color": first["secondary_color"],
        },
    )
    assert created.status_code == 201
    kit = created.get_json()["kit"]
    kit_id = kit["id"]
    assert kit["kit_ref"].startswith("BRD-")
    assert "<svg" in kit["primary_svg"]

    # 6. Update Kit
    patched = client.patch(
        f"/api/brand-studio/kits/{kit_id}",
        headers=hdrs,
        json={"logo_layout": "emblem", "primary_color": "#0b1930"},
    )
    assert patched.status_code == 200
    assert patched.get_json()["kit"]["logo_layout"] == "emblem"
    assert patched.get_json()["kit"]["primary_color"] == "#0b1930"

    # 7. Export SVG + Guidelines JSON
    exp_svg = client.get(f"/api/brand-studio/kits/{kit_id}/export/primary", headers=hdrs)
    assert exp_svg.status_code == 200
    assert exp_svg.mimetype == "image/svg+xml"
    assert b"<svg" in exp_svg.data

    exp_guide = client.get(f"/api/brand-studio/kits/{kit_id}/export/guidelines", headers=hdrs)
    assert exp_guide.status_code == 200
    assert len(exp_guide.get_json()["guidelines"]["colors"]) == 5

    # 8. Publish directly into TRUSTSEAL Media Library
    pub_media = client.post(
        f"/api/brand-studio/kits/{kit_id}/publish-media",
        headers=hdrs,
        json={"variant": "primary"},
    )
    assert pub_media.status_code == 201
    pdata = pub_media.get_json()
    assert pdata["published"] is True
    assert pdata["media_asset"]["category"] == "logo"
    with pg_app.app_context():
        ma = db.session.get(MediaAsset, pdata["media_asset"]["id"])
        assert ma is not None
        assert ma.organization_id == oid
        assert ma.mime_type == "image/svg+xml"

    # 9. Printable Brand Guidelines Book HTML route
    book_page = client.get(f"/brand-studio/guidelines/{kit_id}")
    assert book_page.status_code == 200
    assert b"Vanguard Logistics" in book_page.data
    assert b"Official Color System" in book_page.data

    # 10. Soft-delete Kit
    deleted = client.delete(f"/api/brand-studio/kits/{kit_id}", headers=hdrs)
    assert deleted.status_code == 200
    assert deleted.get_json()["deleted"] is True
