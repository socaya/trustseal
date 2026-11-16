"""Delegated OCSP responder verification (M2)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def _issuer(label: str = "Test Issuer CA"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, label)]
    )
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=0), critical=True
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False,
                key_encipherment=False, data_encipherment=False,
                key_agreement=False, key_cert_sign=True, crl_sign=True,
                encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return key, cert


def _responder(issuer_key, issuer_cert, *, eku=True, digital_signature=True,
               not_before_delta=timedelta(days=-1),
               not_after_delta=timedelta(days=30)):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "Test Responder")]
    )
    now = datetime.now(timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now + not_before_delta)
        .not_valid_after(now + not_after_delta)
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=digital_signature,
                content_commitment=False,
                key_encipherment=False, data_encipherment=False,
                key_agreement=False, key_cert_sign=False, crl_sign=False,
                encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
    )
    if eku:
        builder = builder.add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.OCSP_SIGNING]),
            critical=False,
        )
    return key, builder.sign(issuer_key, hashes.SHA256())


class TestVerifyResponder:
    def test_valid_responder_passes(self):
        from app.services.delegated_ocsp_verify import verify_responder_certificate

        issuer_key, issuer = _issuer()
        _, responder = _responder(issuer_key, issuer)
        check = verify_responder_certificate(responder, issuer)
        assert check.responder_serial == responder.serial_number
        assert check.issuer_serial == issuer.serial_number

    def test_wrong_issuer_fails(self):
        from app.services.delegated_ocsp_verify import (
            DelegatedResponderError,
            verify_responder_certificate,
        )

        issuer_key, issuer = _issuer("Issuer A")
        other_key, other_issuer = _issuer("Issuer B")
        _, responder = _responder(issuer_key, issuer)
        with pytest.raises(DelegatedResponderError) as exc:
            verify_responder_certificate(responder, other_issuer)
        assert "responder_not_issued_by_supplied_issuer" in str(exc.value)

    def test_signature_mismatch_fails(self):
        """A responder signed by a different key — but under the same
        subject — fails signature verification."""
        from app.services.delegated_ocsp_verify import (
            DelegatedResponderError,
            verify_responder_certificate,
        )

        issuer_key, issuer = _issuer()
        # Issuer "A" with its own key, then craft a responder claiming
        # to be signed by A but actually signed by a different key with
        # the same subject.
        rogue_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "Test Responder")]
        )
        now = datetime.now(timezone.utc)
        responder = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer.subject)
            .public_key(rogue_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=30))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None), critical=True
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True, content_commitment=False,
                    key_encipherment=False, data_encipherment=False,
                    key_agreement=False, key_cert_sign=False, crl_sign=False,
                    encipher_only=False, decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.OCSP_SIGNING]),
                critical=False,
            )
            .sign(rogue_key, hashes.SHA256())  # self-signed, not by issuer
        )
        with pytest.raises(DelegatedResponderError) as exc:
            verify_responder_certificate(responder, issuer)
        assert "signature_invalid" in str(exc.value)

    def test_missing_eku_fails(self):
        from app.services.delegated_ocsp_verify import (
            DelegatedResponderError,
            verify_responder_certificate,
        )

        issuer_key, issuer = _issuer()
        _, responder = _responder(issuer_key, issuer, eku=False)
        with pytest.raises(DelegatedResponderError) as exc:
            verify_responder_certificate(responder, issuer)
        assert "missing_eku" in str(exc.value)

    def test_missing_digital_signature_fails(self):
        from app.services.delegated_ocsp_verify import (
            DelegatedResponderError,
            verify_responder_certificate,
        )

        issuer_key, issuer = _issuer()
        _, responder = _responder(
            issuer_key, issuer, digital_signature=False
        )
        with pytest.raises(DelegatedResponderError) as exc:
            verify_responder_certificate(responder, issuer)
        assert "digital_signature" in str(exc.value)

    def test_expired_responder_fails(self):
        from app.services.delegated_ocsp_verify import (
            DelegatedResponderError,
            verify_responder_certificate,
        )

        issuer_key, issuer = _issuer()
        _, responder = _responder(
            issuer_key,
            issuer,
            not_before_delta=timedelta(days=-10),
            not_after_delta=timedelta(days=-1),
        )
        with pytest.raises(DelegatedResponderError) as exc:
            verify_responder_certificate(responder, issuer)
        assert "expired" in str(exc.value)

    def test_not_yet_valid_responder_fails(self):
        from app.services.delegated_ocsp_verify import (
            DelegatedResponderError,
            verify_responder_certificate,
        )

        issuer_key, issuer = _issuer()
        _, responder = _responder(
            issuer_key,
            issuer,
            not_before_delta=timedelta(days=1),
            not_after_delta=timedelta(days=30),
        )
        with pytest.raises(DelegatedResponderError) as exc:
            verify_responder_certificate(responder, issuer)
        assert "not_yet_valid" in str(exc.value)
