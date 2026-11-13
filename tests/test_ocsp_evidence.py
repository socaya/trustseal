"""Real issuer-signed OCSP evidence, chain and historical replay regressions."""
import base64
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509 import ocsp
from cryptography.x509.oid import NameOID

from app.services.ocsp_evidence import (
    OcspEvidenceError, validate_ocsp, verify_ocsp_snapshot,
)


def _certs():
    now = datetime.now(timezone.utc)
    root_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test OCSP issuer")])
    root = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(root_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False,
            key_encipherment=False, data_encipherment=False,
            key_agreement=False, key_cert_sign=True, crl_sign=True,
            encipher_only=False, decipher_only=False,
        ), critical=True)
        .sign(root_key, hashes.SHA256())
    )
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TSA leaf")]))
        .issuer_name(name).public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(now + timedelta(days=30))
        .sign(root_key, hashes.SHA256())
    )
    return root_key, root, leaf


def _response(status=ocsp.OCSPCertStatus.GOOD, *, expired=False, wrong_key=False):
    key, issuer, subject = _certs()
    now = datetime.now(timezone.utc)
    signed = (
        ocsp.OCSPResponseBuilder()
        .add_response(
            cert=subject, issuer=issuer, algorithm=hashes.SHA256(),
            cert_status=status,
            this_update=now - timedelta(days=1),
            next_update=now - timedelta(minutes=1) if expired else now + timedelta(days=1),
            revocation_time=now - timedelta(hours=2) if status == ocsp.OCSPCertStatus.REVOKED else None,
            revocation_reason=x509.ReasonFlags.key_compromise if status == ocsp.OCSPCertStatus.REVOKED else None,
        )
        .responder_id(ocsp.OCSPResponderEncoding.NAME, issuer)
        .sign(
            key if not wrong_key else rsa.generate_private_key(public_exponent=65537, key_size=2048),
            hashes.SHA256(),
        )
        .public_bytes(serialization.Encoding.DER)
    )
    return signed, subject.public_bytes(serialization.Encoding.PEM), issuer.public_bytes(serialization.Encoding.PEM)


def test_valid_ocsp_and_retained_evidence_tamper_detection():
    response, subject, issuer = _response()
    result = validate_ocsp(response, subject, issuer, issuer)
    assert result["status"] == "good"
    snapshot = SimpleNamespace(
        response_der_b64=base64.b64encode(response).decode(),
        subject_der_b64=base64.b64encode(
            x509.load_pem_x509_certificate(subject).public_bytes(serialization.Encoding.DER)
        ).decode(),
        issuer_der_b64=base64.b64encode(
            x509.load_pem_x509_certificate(issuer).public_bytes(serialization.Encoding.DER)
        ).decode(),
        checked_at=result["checked_at"],
        **{name: result[name] for name in (
            "subject_certificate_sha256", "issuer_certificate_sha256",
            "response_sha256", "status", "produced_at", "this_update", "next_update"
        )},
    )
    assert verify_ocsp_snapshot(snapshot, issuer)["status"] == "good"
    snapshot.response_sha256 = "f" * 64
    with pytest.raises(OcspEvidenceError):
        verify_ocsp_snapshot(snapshot, issuer)


@pytest.mark.parametrize("status,result", [
    (ocsp.OCSPCertStatus.REVOKED, "revoked"),
    (ocsp.OCSPCertStatus.UNKNOWN, "unknown"),
])
def test_non_good_cert_status_is_not_converted_to_good(status, result):
    response, subject, issuer = _response(status)
    assert validate_ocsp(response, subject, issuer, issuer)["status"] == result


def test_expired_ocsp_and_forged_issuer_signature_are_rejected():
    response, subject, issuer = _response(expired=True)
    with pytest.raises(OcspEvidenceError):
        validate_ocsp(response, subject, issuer, issuer)
    response, subject, issuer = _response(wrong_key=True)
    with pytest.raises(OcspEvidenceError):
        validate_ocsp(response, subject, issuer, issuer)


def test_wrong_leaf_and_untrusted_root_are_rejected():
    response, subject, issuer = _response()
    _, unrelated_subject, _ = _response()
    with pytest.raises(OcspEvidenceError):
        validate_ocsp(response, unrelated_subject, issuer, issuer)
    _, _, unrelated_root = _response()
    with pytest.raises(OcspEvidenceError):
        validate_ocsp(response, subject, issuer, unrelated_root)
    with pytest.raises(OcspEvidenceError):
        validate_ocsp(b"corrupt", subject, issuer, issuer)
