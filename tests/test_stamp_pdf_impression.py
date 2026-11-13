"""Controlled stamp impression tests on actual PDF bytes."""
from io import BytesIO

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from app.services.stamp_pdf_impression import render_stamped_source
from app.services.platform_pdf_seal import PdfFinalizationError


def source_pdf():
    stream = BytesIO()
    doc = canvas.Canvas(stream, pagesize=(612, 792))
    doc.drawString(70, 700, "Frozen source text")
    doc.showPage()
    doc.save()
    return stream.getvalue()


def render(data=None, **kwargs):
    options = {
        "stamp_code": "ORG-014",
        "stamp_name": "Registered Organization",
        "attestation_id": 187,
        "page_number": 1,
        "x_pt": 350,
        "y_pt": 60,
    }
    options.update(kwargs)
    return render_stamped_source(data if data is not None else source_pdf(), **options)


def test_visible_stamp_contains_full_identity_and_reference():
    result = render()
    assert result.startswith(b"%PDF-")
    reader = PdfReader(BytesIO(result))
    text = reader.pages[0].extract_text()
    for expected in ("Frozen source text", "ORGANIZATIONAL STAMP",
                     "ORG-014", "Registered Organization",
                     "TrustSeal attestation ID: 187"):
        assert expected in text


@pytest.mark.parametrize("change", [
    {"page_number": 0},
    {"page_number": 5},
    {"x_pt": -1},
    {"x_pt": 570},
    {"y_pt": 740},
    {"attestation_id": 0},
    {"stamp_name": "X" * 120},
    {"stamp_name": "\u202eUnsafe unicode"},
])
def test_invalid_stamp_placement_or_identity_is_rejected(change):
    with pytest.raises(PdfFinalizationError):
        render(**change)


def test_rejects_non_pdf_and_previously_signed_source():
    with pytest.raises(PdfFinalizationError):
        render(b"not a PDF")


def test_visual_imprint_and_new_signature_are_bound(signing_config):
    # Integration fixture imported from real cryptographic signing suite.
    from app.services.platform_pdf_seal import seal_pdf, inspect_signed_pdf
    stamped = render()
    sealed, cert_fingerprint, _ = seal_pdf(
        stamped, signing_config, "a" * 64, evidence_purpose="stamp"
    )
    status = inspect_signed_pdf(
        sealed, signing_config, expected_evidence_sha256="a" * 64,
        expected_certificate_sha256=cert_fingerprint,
        evidence_purpose="stamp",
    )
    assert status["overall_valid"]
    with pytest.raises(PdfFinalizationError, match="evidence digest"):
        inspect_signed_pdf(sealed, signing_config, expected_evidence_sha256="a" * 64)
    with pytest.raises(PdfFinalizationError):
        render(sealed)


def test_stamped_source_does_not_mutate_original_bytes():
    original = source_pdf()
    digest_before = __import__("hashlib").sha256(original).hexdigest()
    stamp = render(original)
    assert stamp != original
    assert __import__("hashlib").sha256(original).hexdigest() == digest_before
