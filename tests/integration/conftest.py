"""Disposable certificate authority for real PDF integration tests only."""
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID


def certificate(subject, issuer, public_key, signer_key, is_ca, now):
    builder = (
        x509.CertificateBuilder().subject_name(subject).issuer_name(issuer)
        .public_key(public_key).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(
            x509.BasicConstraints(ca=is_ca, path_length=0 if is_ca else None),
            critical=True,
        )
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
    root_name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Disposable TrustSeal Test Root")
    ])
    root_cert = certificate(
        root_name, root_name, root_key.public_key(), root_key, True, now,
    )
    seal_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    seal_name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Disposable TrustSeal Platform Seal")
    ])
    seal_cert = certificate(
        seal_name, root_name, seal_key.public_key(), root_key, False, now,
    )
    password = b"disposable-test-password"
    bundle = pkcs12.serialize_key_and_certificates(
        b"disposable-seal", seal_key, seal_cert, [root_cert],
        serialization.BestAvailableEncryption(password),
    )
    bundle_path = tmp_path / "seal.p12"
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
