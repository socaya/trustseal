"""Unit tests for TSD-only covert stamp forensics & traceability engine."""
from __future__ import annotations

import hashlib
import io
import re
from datetime import datetime

from PIL import Image
from reportlab.pdfgen import canvas as pdf_canvas

from app.services.tsd_stamp_forensics import (
    PACKET_BYTES,
    compute_forensic_fingerprint,
    embed_png_forensics,
    embed_svg_forensics,
    extract_pdf_forensics,
    extract_png_forensics,
    extract_svg_forensics,
    pack_forensic_packet,
    seal_pdf_bytes,
    strip_forensic_svg_layer,
    unpack_forensic_packet,
)
from app.services.tsd_stamp_receipts import canonicalize_inserted_svg


_KEY_ORG_1 = hashlib.sha256(b"tenant-1-forensic-master-key").digest()
_KEY_ORG_2 = hashlib.sha256(b"tenant-2-forensic-master-key").digest()

_SAMPLE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320">'
    '<circle cx="160" cy="160" r="140" fill="none" stroke="#18345e" stroke-width="4"/>'
    '<text x="160" y="165" text-anchor="middle" fill="#18345e">APPROVED</text>'
    '</svg>'
)


def test_forensic_packet_roundtrip_tamper_and_tenant_isolation():
    ts = datetime(2026, 11, 19, 10, 30, 0)
    pkt = pack_forensic_packet(
        _KEY_ORG_1,
        organization_id=7,
        stamp_id=42,
        receipt_id=991,
        placed_by_id=15,
        document_id=303,
        placed_at=ts,
        nonce="a1b2c3d4e5f60718293a4b5c6d7e8f90",
        channel="tsd_document",
    )
    assert len(pkt) == PACKET_BYTES

    dec = unpack_forensic_packet(_KEY_ORG_1, pkt)
    assert dec is not None
    assert dec.organization_id == 7
    assert dec.stamp_id == 42
    assert dec.receipt_id == 991
    assert dec.placed_by_id == 15
    assert dec.document_id == 303
    assert dec.nonce_prefix == "a1b2c3d4"
    assert dec.channel == "tsd_document"

    # Wrong tenant key cannot decrypt or authenticate
    assert unpack_forensic_packet(_KEY_ORG_2, pkt) is None

    # Flipping a single bit anywhere in the ciphertext/tag fails GCM authentication
    corrupted = bytearray(pkt)
    corrupted[25] ^= 0x01
    assert unpack_forensic_packet(_KEY_ORG_1, bytes(corrupted)) is None


def test_svg_covert_forensics_layers_survival_and_tamper_detection():
    ts = datetime(2026, 11, 19, 11, 0, 0)
    nonce = "deadbeef1234567890abcdef12345678"

    sealed_svg, fp, pkt = embed_svg_forensics(
        _SAMPLE_SVG,
        _KEY_ORG_1,
        organization_id=1,
        stamp_id=12,
        receipt_id=505,
        placed_by_id=3,
        document_id=88,
        placed_at=ts,
        nonce=nonce,
        channel="svg_export",
    )
    assert fp.startswith("TSD-F1-")
    assert len(pkt) == PACKET_BYTES

    # Full extraction detects all 3 covert SVG layers
    fx = extract_svg_forensics(sealed_svg, _KEY_ORG_1)
    assert fx["found"] is True
    assert fx["payload"].receipt_id == 505
    assert fx["payload"].stamp_id == 12
    assert fx["payload"].channel == "svg_export"
    assert fx["micro_text_fingerprint"] == fp
    assert set(fx["layers_detected"]) >= {
        "vector_micro_constellation",
        "vector_micro_path",
        "covert_micro_text_fiber",
    }

    # Stripping data-tsd-f attribute and all circles still recovers via Layer 1B micro-path!
    no_circles = re.sub(r'<circle\b[^>]*r="0\.16"[^>]*/?>', "", sealed_svg)
    no_circles = no_circles.replace(' data-tsd-f="1"', "")
    fx_path = extract_svg_forensics(no_circles, _KEY_ORG_1)
    assert fx_path["found"] is True
    assert fx_path["payload"].receipt_id == 505
    assert "vector_micro_path" in fx_path["layers_detected"]

    # Wrong tenant key cannot decode covert SVG marks
    fx_wrong = extract_svg_forensics(sealed_svg, _KEY_ORG_2)
    assert fx_wrong["found"] is False
    assert fx_wrong["payload"] is None

    # Canonicalization strips forensic layer so artwork hash matches original & detects text tampering
    orig_hash = hashlib.sha256(canonicalize_inserted_svg(_SAMPLE_SVG).encode("utf-8")).hexdigest()
    sealed_canon_hash = hashlib.sha256(canonicalize_inserted_svg(sealed_svg).encode("utf-8")).hexdigest()
    assert orig_hash == sealed_canon_hash

    tampered_svg = sealed_svg.replace("APPROVED", "FORGED")
    tampered_hash = hashlib.sha256(canonicalize_inserted_svg(tampered_svg).encode("utf-8")).hexdigest()
    assert tampered_hash != orig_hash
    # Even when tampered, TSD still extracts the covert receipt to trace who originally issued it
    fx_tampered = extract_svg_forensics(tampered_svg, _KEY_ORG_1)
    assert fx_tampered["found"] is True
    assert fx_tampered["payload"].receipt_id == 505


def test_png_keyed_raster_steganography_survives_metadata_stripping():
    # Create a clean 140x140 PNG stamp image
    img = Image.new("RGBA", (140, 140), (255, 255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw_png = buf.getvalue()

    ts = datetime(2026, 11, 19, 11, 15, 0)
    nonce = "0123456789abcdef0123456789abcdef"
    sealed_png, fp, _ = embed_png_forensics(
        raw_png,
        _KEY_ORG_1,
        organization_id=9,
        stamp_id=21,
        receipt_id=777,
        placed_by_id=4,
        document_id=None,
        placed_at=ts,
        nonce=nonce,
        channel="png_export",
    )
    assert fp == compute_forensic_fingerprint(_KEY_ORG_1, receipt_id=777, stamp_id=21, nonce=nonce)

    # Normal extraction detects both keyed pixel steganography AND PNG chunk
    fx = extract_png_forensics(sealed_png, _KEY_ORG_1)
    assert fx["found"] is True
    assert fx["payload"].receipt_id == 777
    assert fx["payload"].channel == "png_export"
    assert "raster_keyed_steganography" in fx["layers_detected"]
    assert "png_forensic_chunk" in fx["layers_detected"]

    # Strip ALL PNG metadata chunks by re-saving pixels only — pixel steganography MUST survive!
    stripped_img = Image.open(io.BytesIO(sealed_png))
    stripped_buf = io.BytesIO()
    stripped_img.save(stripped_buf, format="PNG")
    stripped_png = stripped_buf.getvalue()

    fx_stripped = extract_png_forensics(stripped_png, _KEY_ORG_1)
    assert fx_stripped["found"] is True
    assert fx_stripped["payload"].receipt_id == 777
    assert "raster_keyed_steganography" in fx_stripped["layers_detected"]
    assert "png_forensic_chunk" not in fx_stripped["layers_detected"]

    # Wrong tenant key cannot read either the keyed pixel permutation or the PNG chunk
    fx_wrong = extract_png_forensics(sealed_png, _KEY_ORG_2)
    assert fx_wrong["found"] is False
    assert fx_wrong["payload"] is None


def test_pdf_layer4_encrypted_forensic_seal_and_isolation():
    ts = datetime(2026, 11, 19, 11, 30, 0)
    nonce = "fedcba9876543210fedcba9876543210"
    pkt = pack_forensic_packet(
        _KEY_ORG_1,
        organization_id=3,
        stamp_id=55,
        receipt_id=888,
        placed_by_id=11,
        document_id=None,
        placed_at=ts,
        nonce=nonce,
        channel="pdf_export",
    )
    fp = compute_forensic_fingerprint(_KEY_ORG_1, receipt_id=888, stamp_id=55, nonce=nonce)

    pdf_buf = io.BytesIO()
    c = pdf_canvas.Canvas(pdf_buf, pagesize=(120, 120))
    c.drawString(10, 60, "TRUSTSEAL STAMP")
    c.showPage()
    c.save()

    sealed_pdf = seal_pdf_bytes(pdf_buf.getvalue(), pkt, fp)

    fx = extract_pdf_forensics(sealed_pdf, _KEY_ORG_1)
    assert fx["found"] is True
    assert fx["payload"].receipt_id == 888
    assert fx["payload"].stamp_id == 55
    assert fx["payload"].channel == "pdf_export"
    assert fx["micro_text_fingerprint"] == fp
    assert "pdf_encrypted_forensic_seal" in fx["layers_detected"]

    # Wrong tenant key cannot decrypt the PDF forensic seal
    fx_wrong = extract_pdf_forensics(sealed_pdf, _KEY_ORG_2)
    assert fx_wrong["found"] is False
    assert fx_wrong["payload"] is None


def test_letterhead_renderer_builds_safe_header_and_footer_for_all_alignments():
    from app.models.tsd_letterhead import (
        LETTERHEAD_PRESETS,
        TSDLetterhead,
        render_letterhead_parts,
    )
    from app.blueprints.estamp.media_letterheads_api import render_letterhead_pdf_bytes

    assert len(LETTERHEAD_PRESETS) >= 5

    for align in ("left", "center", "split", "right"):
        layout = {
            "org_name": "VITALWORKS & CO <LTD>",
            "tagline": "Office of the Secretary",
            "department": "Legal & Governance",
            "address": "14th Floor, Delta Towers",
            "postal_address": "P.O. Box 123, Nairobi",
            "phone": "+254 700 111 222",
            "email": "legal@vitalworks.co",
            "website": "www.vitalworks.co",
            "reg_no": "REG. PVT-99881",
            "tax_id": "PIN P051234567X",
            "directors": "J. Doe, A. Smith",
            "accent_color": "#1e4b9e",
            "header_align": align,
            "divider_style": "double",
            "top_bar_px": 4,
            "show_ref_bar": True,
            "watermark_text": "OFFICIAL",
            "footer_text": "Confidential · Regulated",
            "logo_data_uri": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
            "logo_height_px": 52,
        }
        hdr, ftr = render_letterhead_parts(layout)
        assert "tsd-letterhead-header" in hdr
        assert "tsd-letterhead-footer" in ftr
        assert "tsd-letterhead-ref" in hdr
        assert "VITALWORKS &amp; CO &lt;LTD&gt;" in hdr
        assert "Directors / Officers:" in ftr
        assert "Confidential · Regulated" in ftr

        row = TSDLetterhead(name=f"LH {align}", layout=layout, header_html=hdr, footer_html=ftr)
        pdf_bytes = render_letterhead_pdf_bytes(row)
        assert pdf_bytes.startswith(b"%PDF")
        assert len(pdf_bytes) > 1000
