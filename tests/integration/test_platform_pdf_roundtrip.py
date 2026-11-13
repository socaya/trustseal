"""Staging integration test for real CMS/PAdES PDF seal round-trip.

Uses an ephemeral CA and PKCS#12 generated entirely inside tmp_path.
These keys are test-only and must never be used for production issuance.
Run after installing pyHanko, cryptography and reportlab dependencies.
"""
from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest

import pyhanko  # Required: missing signing dependency must fail, never silently skip.
import reportlab
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from reportlab.pdfgen import canvas

from app.services.platform_pdf_seal import (
    seal_pdf, inspect_signed_pdf, PdfFinalizationError, FIELD_NAME,
)


def _cert(subject, issuer, public_key, signer_key, is_ca, now):
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=is_ca, path_length=0 if is_ca else None), critical=True)
    )
    if is_ca:
        usage = x509.KeyUsage(
            digital_signature=True, content_commitment=False,
            key_encipherment=False, data_encipherment=False,
            key_agreement=False, key_cert_sign=True, crl_sign=True,
            encipher_only=False, decipher_only=False,
        )
    else:
        usage = x509.KeyUsage(
            digital_signature=True, content_commitment=True,
            key_encipherment=False, data_encipherment=False,
            key_agreement=False, key_cert_sign=False, crl_sign=False,
            encipher_only=False, decipher_only=False,
        )
    return builder.add_extension(usage, critical=True).sign(signer_key, hashes.SHA256())


@pytest.fixture
def signing_config(tmp_path):
    now = datetime.now(timezone.utc)
    root_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    root_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TrustSeal Test Root")])
    root_cert = _cert(root_name, root_name, root_key.public_key(), root_key, True, now)
    seal_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    seal_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TrustSeal Test Platform Seal")])
    seal_cert = _cert(seal_name, root_name, seal_key.public_key(), root_key, False, now)
    password = b"test-secret-not-for-production"
    bundle = pkcs12.serialize_key_and_certificates(
        b"trustseal-test-seal", seal_key, seal_cert, [root_cert],
        serialization.BestAvailableEncryption(password),
    )
    bundle_path = tmp_path / "test.p12"
    bundle_path.write_bytes(bundle)
    bundle_path.chmod(0o600)
    root_path = tmp_path / "root.pem"
    root_path.write_bytes(root_cert.public_bytes(serialization.Encoding.PEM))
    return {
        "PDF_PLATFORM_PKCS12": str(bundle_path),
        "PDF_PLATFORM_PKCS12_PASSWORD": password.decode("ascii"),
        "PDF_TRUST_ROOT_PEM": str(root_path),
        "PDF_FINALIZATION_ENABLED": True,
    }


def _sample_pdf():
    buffer = BytesIO()
    c = canvas.Canvas(buffer)
    c.drawString(72, 720, "Test only: TrustSeal certificate-backed platform seal")
    c.showPage()
    c.save()
    return buffer.getvalue()


def test_platform_pdf_roundtrip_and_tamper_rejection(signing_config):
    signed, cert_sha256, checks = seal_pdf(_sample_pdf(), signing_config, "a" * 64)
    assert len(cert_sha256) == 64
    assert checks["field"] == FIELD_NAME
    assert checks["overall_valid"]
    assert inspect_signed_pdf(signed, signing_config, expected_evidence_sha256="a" * 64)["overall_valid"]
    with pytest.raises(PdfFinalizationError, match="evidence digest"):
        inspect_signed_pdf(signed, signing_config, expected_evidence_sha256="b" * 64)

    # Alter a signed byte, leaving the CMS bytes otherwise unchanged.
    modified = bytearray(signed)
    # Mutate document bytes while keeping the original CMS signature intact.
    modified[20] = modified[20] ^ 1
    try:
        verified = inspect_signed_pdf(bytes(modified), signing_config)
    except PdfFinalizationError:
        pass
    else:
        assert not verified["overall_valid"]


def test_signed_source_is_refused_for_single_seal_profile(signing_config):
    sealed, _fingerprint, _status = seal_pdf(_sample_pdf(), signing_config, "a" * 64)
    with pytest.raises(PdfFinalizationError, match="already contains"):
        seal_pdf(sealed, signing_config, "a" * 64)
