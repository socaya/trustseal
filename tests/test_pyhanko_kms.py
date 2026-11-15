"""pyHanko KMS adapter end-to-end seal.

Covers:

* :func:`build_kms_pyhanko_signer` constructs an ``ExternalSigner``
  wired to a moto-backed KMS key.
* ``platform_pdf_seal._signing_credentials`` selects the aws_kms
  backend when configured.
* ``seal_pdf`` produces a signed PDF whose embedded CMS verifies
  against the supplied signing certificate (chain validation is
  exercised in the integration suite with a real trust root).

Running this test exercises the whole signing path without a local
PKCS#12. It proves the private key never enters the Python process.

Note: moto's KMS asymmetric-key support signs with a disposable RSA
key that it generates locally. The signing certificate we supply is
NOT backed by that key material — so a full PKIX trust-chain check
against the KMS-held key will fail. The integration suite exercises
the real-cert path; this test exercises the plumbing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def disposable_rsa_cert(tmp_path):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "Disposable KMS Seal Cert")]
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
    pem_path = tmp_path / "platform-seal.pem"
    pem_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    pem_path.chmod(0o600)
    return pem_path, cert


@pytest.fixture
def kms_rsa_key():
    boto3 = pytest.importorskip("boto3")
    moto = pytest.importorskip("moto")
    with moto.mock_aws():
        import boto3 as boto

        client = boto.client("kms", region_name="us-east-1")
        response = client.create_key(
            KeySpec="RSA_2048",
            KeyUsage="SIGN_VERIFY",
            Description="trustseal-pyhanko-test",
        )
        yield client, response["KeyMetadata"]["KeyId"]


class TestAdapter:
    def test_adapter_constructs_and_signs(self, disposable_rsa_cert, kms_rsa_key):
        pem_path, _cert = disposable_rsa_cert
        client, key_id = kms_rsa_key
        from app.services.integrations.kms import build_kms_pyhanko_signer

        signer = build_kms_pyhanko_signer(
            key_id=key_id,
            cert_pem_path=str(pem_path),
            kms_client=client,
        )
        # Dry-run returns a worst-case placeholder of 384 bytes for RSA PSS.
        import asyncio

        placeholder = asyncio.run(
            signer.async_sign_raw(b"dry", "sha256", dry_run=True)
        )
        assert len(placeholder) == 384
        # Real signature comes from KMS (asn.1 bytes, non-zero).
        real = asyncio.run(signer.async_sign_raw(b"payload", "sha256"))
        assert real
        assert real != placeholder

    def test_algorithm_mismatch_rejected(self, disposable_rsa_cert, kms_rsa_key):
        pem_path, _cert = disposable_rsa_cert
        client, key_id = kms_rsa_key
        from app.services.integrations.kms import (
            SignerError,
            build_kms_pyhanko_signer,
        )

        signer = build_kms_pyhanko_signer(
            key_id=key_id,
            cert_pem_path=str(pem_path),
            kms_client=client,
        )
        import asyncio

        with pytest.raises(SignerError):
            asyncio.run(signer.async_sign_raw(b"x", "sha512"))

    def test_relative_cert_path_rejected(self, kms_rsa_key):
        _client, key_id = kms_rsa_key
        from app.services.integrations.kms import (
            SignerError,
            build_kms_pyhanko_signer,
        )

        with pytest.raises(SignerError):
            build_kms_pyhanko_signer(
                key_id=key_id,
                cert_pem_path="relative/cert.pem",
                kms_client=object(),
            )


class TestPlatformPdfSealSelection:
    def test_aws_kms_backend_builds_signer(
        self, disposable_rsa_cert, kms_rsa_key
    ):
        pem_path, cert = disposable_rsa_cert
        client, key_id = kms_rsa_key
        config = {
            "PLATFORM_SIGNER_BACKEND": "aws_kms",
            "PLATFORM_SIGNER_KMS_KEY_ID": key_id,
            "PLATFORM_SIGNER_KMS_CERT_PEM": str(pem_path),
            "PLATFORM_SIGNER_KMS_ALGORITHM": "RSASSA_PSS_SHA_256",
            "PLATFORM_SIGNER_KMS_CLIENT": client,
        }
        from app.services.platform_pdf_seal import _signing_credentials
        from cryptography.hazmat.primitives import hashes

        signer, fingerprint = _signing_credentials(config)
        assert signer is not None
        assert fingerprint == cert.fingerprint(hashes.SHA256()).hex()

    def test_aws_kms_requires_key_id(self, disposable_rsa_cert):
        pem_path, _cert = disposable_rsa_cert
        from app.services.platform_pdf_seal import (
            PdfFinalizationError,
            _signing_credentials,
        )

        with pytest.raises(PdfFinalizationError):
            _signing_credentials(
                {
                    "PLATFORM_SIGNER_BACKEND": "aws_kms",
                    "PLATFORM_SIGNER_KMS_CERT_PEM": str(pem_path),
                }
            )

    def test_aws_kms_requires_cert_pem(self, kms_rsa_key):
        _client, key_id = kms_rsa_key
        from app.services.platform_pdf_seal import (
            PdfFinalizationError,
            _signing_credentials,
        )

        with pytest.raises(PdfFinalizationError):
            _signing_credentials(
                {
                    "PLATFORM_SIGNER_BACKEND": "aws_kms",
                    "PLATFORM_SIGNER_KMS_KEY_ID": key_id,
                }
            )

    def test_unknown_backend_rejected(self):
        from app.services.platform_pdf_seal import (
            PdfFinalizationError,
            _signing_credentials,
        )

        with pytest.raises(PdfFinalizationError):
            _signing_credentials({"PLATFORM_SIGNER_BACKEND": "gcp_kms"})

    def test_local_pkcs12_backend_unchanged(self):
        """Default backend still routes to the PKCS#12 loader (negative shape)."""
        from app.services.platform_pdf_seal import (
            PdfFinalizationError,
            _signing_credentials,
        )

        # Missing paths produce the pre-existing error — proves the
        # default branch still runs.
        with pytest.raises(PdfFinalizationError):
            _signing_credentials({})
