"""Tests for TSD stamp receipts, verification, templates, duplicate."""
from __future__ import annotations

import pytest

from app.extensions import db
from app.models.organization import Organization
from app.models.tsd_stamp import TSDStamp
from app.models.user import User


_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle r="4" cx="5" cy="5"/></svg>'


@pytest.fixture
def stamped_tenant(pg_app):
    org_a = Organization(name="StampCo A")
    org_b = Organization(name="StampCo B")
    db.session.add_all([org_a, org_b])
    db.session.flush()
    u = User(username="stamper", email="s@a.test", first_name="S",
             last_name="A", is_active=True, organization_id=org_a.id)
    u.set_password("stamper-password-tests-only")
    u_b = User(username="stamperb", email="s@b.test", first_name="S",
               last_name="B", is_active=True, organization_id=org_b.id)
    u_b.set_password("stamper-password-tests-only")
    db.session.add_all([u, u_b])
    db.session.flush()
    s = TSDStamp(organization_id=org_a.id, created_by_id=u.id,
                 name="Round Seal", kind="seal",
                 layout={"top": "COMPANY"}, svg=_SVG)
    db.session.add(s)
    db.session.commit()
    return {"org_a": org_a.id, "org_b": org_b.id,
            "user_a": u.id, "user_b": u_b.id, "stamp_id": s.id}


def test_receipt_issue_and_verify(pg_app, stamped_tenant):
    from app.services.tsd_stamp_receipts import issue_receipt, verify_receipt

    stamp = db.session.get(TSDStamp, stamped_tenant["stamp_id"])
    r = issue_receipt(
        organization_id=stamped_tenant["org_a"],
        stamp=stamp,
        placed_by_id=stamped_tenant["user_a"],
        document_id=None,
        context_label="Signature block",
        context_svg=_SVG,
    )
    db.session.commit()

    good = verify_receipt(
        organization_id=stamped_tenant["org_a"],
        receipt_id=r.id, nonce=r.nonce, context_svg=_SVG,
    )
    assert good["valid"] is True
    assert good["stamp_name"] == "Round Seal"
    assert good["context_intact"] is True


def test_receipt_bad_nonce_fails(pg_app, stamped_tenant):
    from app.services.tsd_stamp_receipts import issue_receipt, verify_receipt

    stamp = db.session.get(TSDStamp, stamped_tenant["stamp_id"])
    r = issue_receipt(
        organization_id=stamped_tenant["org_a"],
        stamp=stamp, placed_by_id=stamped_tenant["user_a"],
        document_id=None, context_label=None, context_svg=_SVG,
    )
    db.session.commit()

    bad = verify_receipt(
        organization_id=stamped_tenant["org_a"],
        receipt_id=r.id, nonce="0" * 32, context_svg=_SVG,
    )
    assert bad["valid"] is False
    assert bad["reason"] == "nonce_mismatch"


def test_receipt_rejects_tampered_svg(pg_app, stamped_tenant):
    from app.services.tsd_stamp_receipts import issue_receipt, verify_receipt

    stamp = db.session.get(TSDStamp, stamped_tenant["stamp_id"])
    r = issue_receipt(
        organization_id=stamped_tenant["org_a"],
        stamp=stamp, placed_by_id=stamped_tenant["user_a"],
        document_id=None, context_label=None, context_svg=_SVG,
    )
    db.session.commit()

    tampered_svg = _SVG.replace("CRL", "X")  # same text; actually just alter it
    tampered_svg = _SVG.replace("<circle r=\"4\"", "<circle r=\"5\"")
    assert tampered_svg != _SVG

    out = verify_receipt(
        organization_id=stamped_tenant["org_a"],
        receipt_id=r.id, nonce=r.nonce, context_svg=tampered_svg,
    )
    # Signature is still valid — only context_intact flips false.
    assert out["valid"] is True
    assert out["context_intact"] is False


def test_receipt_tenant_isolation(pg_app, stamped_tenant):
    from app.services.tsd_stamp_receipts import issue_receipt, verify_receipt

    stamp = db.session.get(TSDStamp, stamped_tenant["stamp_id"])
    r = issue_receipt(
        organization_id=stamped_tenant["org_a"],
        stamp=stamp, placed_by_id=stamped_tenant["user_a"],
        document_id=None, context_label=None, context_svg=_SVG,
    )
    db.session.commit()

    # Tenant B must not be able to verify tenant A's receipt.
    bad = verify_receipt(
        organization_id=stamped_tenant["org_b"],
        receipt_id=r.id, nonce=r.nonce, context_svg=_SVG,
    )
    assert bad["valid"] is False
    assert bad["reason"] in ("receipt_not_found", "signature_mismatch")


def test_templates_catalogue_has_ten():
    from app.services import tsd_stamp_templates

    items = tsd_stamp_templates.list_templates()
    slugs = {t["slug"] for t in items}
    assert len(items) >= 8
    assert {"corporate-seal", "notary-seal", "company-dated",
            "received-stamp", "approved-stamp", "draft-watermark",
            "confidential-stamp", "copy-stamp"} <= slugs
    for t in items:
        assert t["svg"].startswith("<svg")
        assert t["svg"].endswith("</svg>")


def test_public_verify_endpoints(pg_app, stamped_tenant):
    """Unauthenticated GET /verify/stamp/<id>/<nonce> validates a receipt."""
    from app.services.tsd_stamp_receipts import issue_receipt

    stamp = db.session.get(TSDStamp, stamped_tenant["stamp_id"])
    r = issue_receipt(
        organization_id=stamped_tenant["org_a"],
        stamp=stamp, placed_by_id=stamped_tenant["user_a"],
        document_id=None, context_label="Approval block", context_svg=_SVG,
    )
    db.session.commit()

    client = pg_app.test_client()
    j = client.get(
        f"/verify/stamp/{r.id}/{r.nonce}",
        headers={"Accept": "application/json"},
    )
    assert j.status_code == 200
    body = j.get_json()
    assert body["valid"] is True
    assert body["stamp_name"] == "Round Seal"
    # Leaked internals are off-limits.
    assert "placed_by_id" not in body
    assert "document_id" not in body

    # Bad nonce → not-found (self-authorising URL).
    bad = client.get(
        f"/verify/stamp/{r.id}/{'0' * 32}",
        headers={"Accept": "application/json"},
    )
    assert bad.status_code == 400
    assert bad.get_json()["valid"] is False

    # Missing receipt → 404.
    miss = client.get(
        "/verify/stamp/999999/deadbeefdeadbeefdeadbeefdeadbeef",
        headers={"Accept": "application/json"},
    )
    assert miss.status_code == 404

    # QR endpoint returns SVG for a valid receipt.
    qr = client.get(f"/verify/stamp/qr/{r.id}/{r.nonce}.svg")
    assert qr.status_code == 200
    assert qr.mimetype == "image/svg+xml"
    assert b"<svg" in qr.data


def test_canonicalize_strips_receipt_attrs():
    from app.services.tsd_stamp_receipts import canonicalize_inserted_svg

    tagged = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'data-stamp-receipt-id="42" data-stamp-receipt-nonce="abcdef0123456789abcdef0123456789" '
        'data-stamp-placed-at="2026-11-18T01:02:03" data-stamp-placed-by="7" '
        'viewBox="0 0 10 10"><circle/></svg>'
    )
    cleaned = canonicalize_inserted_svg(tagged)
    assert "data-stamp-receipt-id" not in cleaned
    assert "data-stamp-receipt-nonce" not in cleaned
    assert "data-stamp-placed-at" not in cleaned
    assert "data-stamp-placed-by" not in cleaned
    assert "viewBox" in cleaned


@pytest.mark.parametrize(("kind", "layout", "expected"), [
    ("seal", {"shape": "circle", "size_value": "42"}, (42.0, 42.0)),
    ("seal", {"shape": "rectangle", "size_value": "70x25"}, (70.0, 25.0)),
    ("company_dated", {"shape": "oval", "width_mm": 45, "height_mm": 30}, (45.0, 30.0)),
    ("rubber", {"size_value": "58x22"}, (58.0, 22.0)),
    ("date", {"size_value": "custom", "custom_w": 75, "custom_h": 38}, (75.0, 38.0)),
    ("company_rect", {"width_mm": 100, "height_mm": 50}, (100.0, 50.0)),
])
def test_stamp_dimensions_mm_resolves_shape_aware_and_legacy_layouts(kind, layout, expected):
    from app.blueprints.estamp.tsd_stamps_api import _stamp_dimensions_mm

    assert _stamp_dimensions_mm(kind, layout) == expected


def test_stamp_dimensions_mm_clamps_invalid_physical_sizes():
    from app.blueprints.estamp.tsd_stamps_api import _stamp_dimensions_mm

    assert _stamp_dimensions_mm("seal", {"width_mm": 0, "height_mm": 999}) == (5.0, 300.0)


def test_all_templates_have_valid_xml_svg_unique_slugs_and_layouts():
    import xml.etree.ElementTree as ET
    from app.services import tsd_stamp_templates

    templates = tsd_stamp_templates.list_templates()
    assert len(templates) >= 70
    valid_kinds = {"seal", "company_dated", "company_rect", "date", "rubber", "signature"}
    slugs = set()
    for t in templates:
        slug = t["slug"]
        assert slug not in slugs, f"Duplicate template slug: {slug}"
        slugs.add(slug)
        assert t["kind"] in valid_kinds, f"Unexpected kind on {slug}: {t['kind']}"
        assert isinstance(t.get("layout"), dict) and len(t["layout"]) > 0, f"Missing layout on {slug}"
        root = ET.fromstring(t["svg"])
        assert root.tag.endswith("svg"), f"Invalid SVG root on {slug}"


def test_corporate_general_and_industry_templates_present_with_dimensions():
    from app.services import tsd_stamp_templates
    from app.blueprints.estamp.tsd_stamps_api import _stamp_dimensions_mm

    by_slug = {t["slug"]: t for t in tsd_stamp_templates.list_templates()}
    expected_slugs = [
        "corp-rect-official-seal",
        "corp-rect-director-sign",
        "general-company-oval-seal",
        "general-company-rubber-rect",
        "general-company-rubber-circle",
        "general-company-rubber-hexagon",
        "std-accounting-posting-voucher",
        "std-bank-deposit-only",
        "std-notary-jurat-block",
        "std-medical-practitioner",
        "std-engineering-drawing-approval",
    ]
    for slug in expected_slugs:
        assert slug in by_slug, f"Missing expected template: {slug}"
        t = by_slug[slug]
        w, h = _stamp_dimensions_mm(t["kind"], t["layout"])
        assert 5.0 <= w <= 300.0 and 5.0 <= h <= 300.0
