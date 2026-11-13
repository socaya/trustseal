"""Artwork validation, immutability and canonical design digests."""
import base64
import io

import pytest
from PIL import Image

from app.services.stamp_designs import (
    validate_layout, normalize_png, design_digest, checked_design,
)
from app.services.stamp_pdf_impression import preview_stamp_pdf
from types import SimpleNamespace

LAYOUT = {"size": "wide", "ink": "blue", "border": "rectangle"}


def png_artwork():
    out = io.BytesIO()
    Image.new("RGBA", (64, 64), (20, 60, 120, 255)).save(out, format="PNG")
    return base64.b64encode(out.getvalue()).decode("ascii")


def test_png_is_normalized_and_hashed_deterministically():
    normalized, fingerprint = normalize_png(png_artwork())
    again, digest = normalize_png(normalized)
    assert normalized == again
    assert fingerprint == digest
    record = SimpleNamespace(
        layout=dict(LAYOUT), logo_png_b64=normalized,
        logo_sha256=fingerprint,
        design_sha256=design_digest(LAYOUT, fingerprint),
    )
    checked, raw = checked_design(record)
    assert checked == LAYOUT
    assert raw.startswith(b"\x89PNG")
    sample = preview_stamp_pdf("VW-001", "Vitalworks Limited", 2, checked, raw)
    assert sample.startswith(b"%PDF-")


def test_changed_logo_or_style_invalidates_design():
    normalized, fingerprint = normalize_png(png_artwork())
    record = SimpleNamespace(
        layout=dict(LAYOUT), logo_png_b64=normalized,
        logo_sha256=fingerprint,
        design_sha256=design_digest(LAYOUT, fingerprint),
    )
    record.layout = {**LAYOUT, "ink": "black"}
    with pytest.raises(ValueError):
        checked_design(record)


@pytest.mark.parametrize("layout", [
    {"size": "wide", "ink": "blue"},
    {"size": "oversize", "ink": "blue", "border": "none"},
    {"size": "wide", "ink": "red", "border": "none"},
    {"size": "wide", "ink": "blue", "border": "<svg>"},
    {"size": "wide", "ink": "blue", "border": "none", "font": "external"},
])
def test_rejects_unapproved_layout_options(layout):
    with pytest.raises(ValueError):
        validate_layout(layout)


def test_non_png_and_oversized_png_rejected():
    for payload in ("not-base64", base64.b64encode(b"<svg></svg>").decode()):
        with pytest.raises(ValueError):
            normalize_png(payload)
    bad = io.BytesIO()
    Image.new("RGBA", (700, 700), (0, 0, 0, 0)).save(bad, format="PNG")
    with pytest.raises(ValueError):
        normalize_png(base64.b64encode(bad.getvalue()).decode())
