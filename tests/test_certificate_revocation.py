"""Real signed X.509 CRL evidence with certificate-chain and tamper tests."""
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.services.certificate_revocation import (
    RevocationEvidenceError, validate_crl, verify_snapshot,
)


def _material(revoked=False, valid=True, foreign_issuer=False):
    now = datetime.now(timezone.utc)
    issuer_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CRL Root")])
    issuer = (
        x509.CertificateBuilder()
        .subject_name(issuer_name).issuer_name(issuer_name)
        .public_key(issuer_key.public_key()).serial_number(100)
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False,
            key_encipherment=False, data_encipherment=False,
            key_agreement=False, key_cert_sign=True, crl_sign=True,
            encipher_only=False, decipher_only=False,
        ), critical=True)
        .sign(issuer_key, hashes.SHA256())
    )
    signer_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signer = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test TSA")]))
        .issuer_name(issuer_name).public_key(signer_key.public_key())
        .serial_number(200)
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(now + timedelta(days=30))
        .sign(issuer_key, hashes.SHA256())
    )
    builder = (
        x509.CertificateRevocationListBuilder()
        .issuer_name(issuer_name)
        .last_update(now - timedelta(days=2 if not valid else 1))
        .next_update(now - timedelta(hours=1) if not valid else now + timedelta(days=2))
    )
    if revoked:
        entry = (
            x509.RevokedCertificateBuilder()
            .serial_number(signer.serial_number)
            .revocation_date(now - timedelta(hours=3))
            .build()
        )
        builder = builder.add_revoked_certificate(entry)
    if foreign_issuer:
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        crl = builder.sign(other_key, hashes.SHA256())
    else:
        crl = builder.sign(issuer_key, hashes.SHA256())
    return (
        crl.public_bytes(serialization.Encoding.DER),
        signer.public_bytes(serialization.Encoding.PEM),
        issuer.public_bytes(serialization.Encoding.PEM),
    )


def test_valid_signed_crl_observation_and_offline_snapshot():
    raw, signer, issuer = _material()
    result = validate_crl(raw, signer, issuer, issuer)
    assert result["status"] == "good"
    assert result["crl_sha256"] == hashlib.sha256(raw).hexdigest()
    snapshot = SimpleNamespace(
        crl_der_b64=base64.b64encode(raw).decode(),
        subject_der_b64=base64.b64encode(
            x509.load_pem_x509_certificate(signer).public_bytes(serialization.Encoding.DER)
        ).decode(),
        issuer_der_b64=base64.b64encode(
            x509.load_pem_x509_certificate(issuer).public_bytes(serialization.Encoding.DER)
        ).decode(),
        checked_at=result["checked_at"], **{
            name: result[name] for name in (
                "subject_certificate_sha256", "issuer_certificate_sha256",
                "crl_sha256", "status", "this_update", "next_update"
            )
        },
    )
    assert verify_snapshot(snapshot, issuer)["status"] == "good"
    snapshot.crl_sha256 = "f" * 64
    with pytest.raises(RevocationEvidenceError):
        verify_snapshot(snapshot, issuer)


def test_revoked_cert_is_explicitly_reported():
    raw, signer, issuer = _material(revoked=True)
    assert validate_crl(raw, signer, issuer, issuer)["status"] == "revoked"


def test_expired_crl_rejected():
    raw, signer, issuer = _material(valid=False)
    with pytest.raises(RevocationEvidenceError, match="not valid"):
        validate_crl(raw, signer, issuer, issuer)


def test_invalid_crl_signature_rejected():
    raw, signer, issuer = _material(foreign_issuer=True)
    with pytest.raises(RevocationEvidenceError, match="signature"):
        validate_crl(raw, signer, issuer, issuer)


def test_wrong_issuer_and_truncated_encoding_rejected():
    raw, signer, issuer = _material()
    _, _, different_root = _material()
    with pytest.raises(RevocationEvidenceError):
        validate_crl(raw, signer, different_root, different_root)
    with pytest.raises(RevocationEvidenceError):
        validate_crl(b"invalid", signer, issuer, issuer)
