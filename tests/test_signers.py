"""Signer interface contract tests.

All three concrete signers (LocalEd25519, LocalPkcs12, AwsKms) satisfy
the same :class:`Signer` interface. The tests here prove:

* ``sign`` returns a :class:`SignatureEnvelope` with the declared
  algorithm.
* The signature verifies against the signer's public key / certificate.
* ``key_identifier`` is stable and non-empty.
* Backend-specific failures surface as :class:`SignerError`.
* The factory honours ``RECEIPT_SIGNER_BACKEND`` selection.

AWS KMS is exercised via moto so no credentials or network are needed.
"""
from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    pkcs12 as pkcs12_mod,
    BestAvailableEncryption,
)

from app.services.integrations.kms import (
    AlgorithmUnsupported,
    AwsKmsSigner,
    LocalEd25519Signer,
    LocalPkcs12Signer,
    SignatureEnvelope,
    SignerError,
    build_detached_signer,
)


# --- fixtures -------------------------------------------------------


@pytest.fixture
def ed25519_key(tmp_path):
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path = tmp_path / "ed25519.pem"
    path.write_bytes(pem)
    path.chmod(0o600)
    return path, key


@pytest.fixture
def rsa_pkcs12(tmp_path):
    """Build a minimal self-signed PKCS#12 bundle for tests."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from datetime import datetime, timedelta, timezone

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "Disposable PKCS12 Test")]
    )
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    password = b"disposable-test-password"
    bundle = pkcs12_mod.serialize_key_and_certificates(
        b"disposable",
        key,
        cert,
        [],
        BestAvailableEncryption(password),
    )
    path = tmp_path / "bundle.p12"
    path.write_bytes(bundle)
    path.chmod(0o600)
    return path, password.decode("ascii"), key, cert


@pytest.fixture
def kms():
    boto3 = pytest.importorskip("boto3")
    moto = pytest.importorskip("moto")
    with moto.mock_aws():
        import boto3 as boto

        client = boto.client("kms", region_name="us-east-1")
        response = client.create_key(
            KeySpec="RSA_2048",
            KeyUsage="SIGN_VERIFY",
            Description="trustseal-test",
        )
        key_id = response["KeyMetadata"]["KeyId"]
        yield client, key_id


# --- LocalEd25519Signer --------------------------------------------


class TestLocalEd25519Signer:
    def test_sign_verifies_with_public_key(self, ed25519_key):
        path, key = ed25519_key
        signer = LocalEd25519Signer(str(path))
        envelope = signer.sign(b"payload")
        assert isinstance(envelope, SignatureEnvelope)
        assert envelope.algorithm == "Ed25519"
        key.public_key().verify(envelope.signature, b"payload")
        assert signer.key_identifier().startswith("ed25519-sha256:")

    def test_rejects_relative_path(self):
        with pytest.raises(SignerError):
            LocalEd25519Signer("relative/path")

    def test_rejects_world_readable(self, ed25519_key):
        path, _key = ed25519_key
        path.chmod(0o644)
        with pytest.raises(SignerError):
            LocalEd25519Signer(str(path))

    def test_rejects_non_ed25519_pem(self, rsa_pkcs12, tmp_path):
        _p, _pwd, rsa_key, _cert = rsa_pkcs12
        pem = rsa_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        path = tmp_path / "rsa.pem"
        path.write_bytes(pem)
        path.chmod(0o600)
        with pytest.raises(SignerError):
            LocalEd25519Signer(str(path))


# --- LocalPkcs12Signer ---------------------------------------------


class TestLocalPkcs12Signer:
    def test_sign_verifies_rsa_pss(self, rsa_pkcs12):
        path, password, key, cert = rsa_pkcs12
        signer = LocalPkcs12Signer(str(path), password)
        assert signer.algorithm() == "RSASSA_PSS_SHA256"
        envelope = signer.sign(b"payload")
        key.public_key().verify(
            envelope.signature,
            b"payload",
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
            hashes.SHA256(),
        )
        assert signer.certificate_fingerprint == cert.fingerprint(hashes.SHA256()).hex()
        assert signer.public_certificate_pem().startswith(b"-----BEGIN CERTIFICATE-----")

    def test_wrong_password_rejected(self, rsa_pkcs12):
        path, _password, _k, _c = rsa_pkcs12
        with pytest.raises(SignerError):
            LocalPkcs12Signer(str(path), "wrong-password")

    def test_missing_password_rejected(self, rsa_pkcs12):
        path, _password, _k, _c = rsa_pkcs12
        with pytest.raises(SignerError):
            LocalPkcs12Signer(str(path), "")

    def test_relative_path_rejected(self):
        with pytest.raises(SignerError):
            LocalPkcs12Signer("relative.p12", "pwd")


# --- AwsKmsSigner ---------------------------------------------------


class TestAwsKmsSigner:
    def test_sign_matches_kms_verify(self, kms):
        client, key_id = kms
        signer = AwsKmsSigner(
            key_id=key_id,
            signing_algorithm="RSASSA_PSS_SHA_256",
            client=client,
        )
        envelope = signer.sign(b"payload")
        assert envelope.algorithm == "RSASSA_PSS_SHA256"
        assert envelope.key_identifier == key_id
        import hashlib

        digest = hashlib.sha256(b"payload").digest()
        verify = client.verify(
            KeyId=key_id,
            Message=digest,
            MessageType="DIGEST",
            Signature=envelope.signature,
            SigningAlgorithm="RSASSA_PSS_SHA_256",
        )
        assert verify["SignatureValid"] is True

    def test_public_key_der_round_trip(self, kms):
        client, key_id = kms
        signer = AwsKmsSigner(key_id=key_id, client=client)
        der = signer.public_key_der()
        from cryptography.hazmat.primitives import serialization as sz

        loaded = sz.load_der_public_key(der)
        assert loaded is not None

    def test_unsupported_algorithm_rejected(self, kms):
        _c, key_id = kms
        with pytest.raises(AlgorithmUnsupported):
            AwsKmsSigner(key_id=key_id, signing_algorithm="Ed25519")

    def test_empty_key_id_rejected(self):
        with pytest.raises(SignerError):
            AwsKmsSigner(key_id="")

    def test_non_bytes_payload_rejected(self, kms):
        client, key_id = kms
        signer = AwsKmsSigner(key_id=key_id, client=client)
        with pytest.raises(SignerError):
            signer.sign("not bytes")  # type: ignore[arg-type]


# --- factory --------------------------------------------------------


class TestFactory:
    def test_local_ed25519_default(self, ed25519_key):
        path, _k = ed25519_key
        signer = build_detached_signer(
            {"REVIEW_RECEIPT_PRIVATE_KEY": str(path)}
        )
        assert signer.algorithm() == "Ed25519"

    def test_local_ed25519_requires_path(self):
        with pytest.raises(SignerError):
            build_detached_signer({"RECEIPT_SIGNER_BACKEND": "local_ed25519"})

    def test_aws_kms_requires_key_id(self):
        with pytest.raises(SignerError):
            build_detached_signer({"RECEIPT_SIGNER_BACKEND": "aws_kms"})

    def test_unknown_backend_rejected(self):
        with pytest.raises(SignerError):
            build_detached_signer({"RECEIPT_SIGNER_BACKEND": "gcp_kms"})
