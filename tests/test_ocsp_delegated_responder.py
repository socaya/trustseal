"""Actual delegated OCSP signer authorization, integrity and replay tests."""
import base64
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509 import ocsp
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID

from app.services.ocsp_evidence import (
    OcspEvidenceError, validate_ocsp, verify_ocsp_snapshot,
)


def _signed_response(*, allow_ocsp=True, tamper=False, responder_expired=False,
                     responder_ca=False, include_signer=True):
    now = datetime.now(timezone.utc)
    issuer_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer_name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Isolated Delegated OCSP Root")
    ])
    issuer = (
        x509.CertificateBuilder()
        .subject_name(issuer_name).issuer_name(issuer_name)
        .public_key(issuer_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=3))
        .not_valid_after(now + timedelta(days=90))
        .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False,
            key_encipherment=False, data_encipherment=False,
            key_agreement=False, key_cert_sign=True, crl_sign=True,
            encipher_only=False, decipher_only=False,
        ), critical=True)
        .sign(issuer_key, hashes.SHA256())
    )
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TSA leaf")]))
        .issuer_name(issuer_name).public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(now + timedelta(days=90))
        .sign(issuer_key, hashes.SHA256())
    )
    responder_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    responder_name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Authorized OCSP Responder")
    ])
    responder_builder = (
        x509.CertificateBuilder()
        .subject_name(responder_name).issuer_name(issuer_name)
        .public_key(responder_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=30) if responder_expired else now - timedelta(days=1))
        .not_valid_after(now - timedelta(days=1) if responder_expired else now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=responder_ca, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False,
            key_encipherment=False, data_encipherment=False,
            key_agreement=False, key_cert_sign=responder_ca, crl_sign=False,
            encipher_only=False, decipher_only=False,
        ), critical=True)
    )
    if allow_ocsp:
        responder_builder = responder_builder.add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.OCSP_SIGNING]), critical=False
        )
    responder = responder_builder.sign(issuer_key, hashes.SHA256())
    builder = (
        ocsp.OCSPResponseBuilder()
        .add_response(
            cert=leaf, issuer=issuer, algorithm=hashes.SHA256(),
            cert_status=ocsp.OCSPCertStatus.GOOD,
            this_update=now - timedelta(hours=1),
            next_update=now + timedelta(hours=12),
            revocation_time=None, revocation_reason=None,
        )
        .responder_id(ocsp.OCSPResponderEncoding.NAME, responder)
    )
    if include_signer:
        builder = builder.certificates([responder])
    raw = builder.sign(responder_key, hashes.SHA256()).public_bytes(
        serialization.Encoding.DER
    )
    if tamper:
        raw = raw[:-1] + bytes([raw[-1] ^ 1])
    return raw, leaf.public_bytes(serialization.Encoding.PEM), issuer.public_bytes(
        serialization.Encoding.PEM
    )


def test_authorized_delegated_ocsp_signer_replays_from_retained_certificate():
    raw, subject, issuer = _signed_response()
    result = validate_ocsp(raw, subject, issuer, issuer)
    assert result["status"] == "good"
    assert result["delegated"] is True
    assert result["responder_certificate_sha256"] != result["issuer_certificate_sha256"]
    snapshot = SimpleNamespace(
        response_der_b64=base64.b64encode(raw).decode(),
        subject_der_b64=base64.b64encode(
            x509.load_pem_x509_certificate(subject).public_bytes(serialization.Encoding.DER)
        ).decode(),
        issuer_der_b64=base64.b64encode(
            x509.load_pem_x509_certificate(issuer).public_bytes(serialization.Encoding.DER)
        ).decode(),
        responder_der_b64=result["responder_der_b64"],
        responder_certificate_sha256=result["responder_certificate_sha256"],
        checked_at=result["checked_at"],
        **{name: result[name] for name in (
            "subject_certificate_sha256", "issuer_certificate_sha256",
            "response_sha256", "status", "produced_at", "this_update", "next_update"
        )},
    )
    assert verify_ocsp_snapshot(snapshot, issuer)["delegated"]
    snapshot.responder_certificate_sha256 = "a" * 64
    with pytest.raises(OcspEvidenceError):
        verify_ocsp_snapshot(snapshot, issuer)


@pytest.mark.parametrize("options", [
    {"allow_ocsp": False},
    {"responder_expired": True},
    {"responder_ca": True},
    {"include_signer": False},
    {"tamper": True},
])
def test_delegated_responder_fails_closed_when_untrusted(options):
    raw, leaf, issuer = _signed_response(**options)
    with pytest.raises(OcspEvidenceError):
        validate_ocsp(raw, leaf, issuer, issuer)


def test_historical_delegated_response_without_retained_cert_is_rejected():
    raw, leaf, issuer = _signed_response()
    result = validate_ocsp(raw, leaf, issuer, issuer)
    historical = SimpleNamespace(
        response_der_b64=base64.b64encode(raw).decode(),
        subject_der_b64=base64.b64encode(
            x509.load_pem_x509_certificate(leaf).public_bytes(serialization.Encoding.DER)
        ).decode(),
        issuer_der_b64=base64.b64encode(
            x509.load_pem_x509_certificate(issuer).public_bytes(serialization.Encoding.DER)
        ).decode(),
        checked_at=result["checked_at"],
        **{field: result[field] for field in (
            "subject_certificate_sha256", "issuer_certificate_sha256",
            "response_sha256", "status", "produced_at", "this_update", "next_update"
        )},
    )
    with pytest.raises(OcspEvidenceError):
        verify_ocsp_snapshot(historical, issuer)
