"""pyHanko ``ExternalSigner`` backed by AWS KMS.

Produces PDF CMS signatures using a private key that never leaves KMS.
The signing certificate is supplied as a PEM file (operator-configured
and typically rotated through ``flask keys rotate``, see ADR 0001).

Usage pattern:

    pyhanko_signer = build_kms_pyhanko_signer(
        key_id="arn:aws:kms:...:key/abc",
        cert_pem_path="/opt/trustseal/certs/platform-seal.pem",
        extra_certs_pem_paths=["/opt/trustseal/certs/platform-chain.pem"],
    )

The returned object plugs directly into
``pyhanko.sign.signers.PdfSigner`` and the existing
``platform_pdf_seal.seal_pdf`` call path.

Testing uses moto's in-process KMS mock so no real AWS credentials and
no live network are needed. See ``tests/test_pyhanko_kms.py``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from asn1crypto import algos as asn_algos
from asn1crypto import x509 as asn_x509
from pyhanko.sign.signers import ExternalSigner
from pyhanko_certvalidator.registry import SimpleCertificateStore

from .aws_kms import AwsKmsSigner
from .base import AlgorithmUnsupported, SignerError

# KMS signing algorithms → pyHanko-accepted digest algorithm names.
_DIGEST_FOR_ALGORITHM = {
    "RSASSA_PSS_SHA256": "sha256",
    "ECDSA_SHA256": "sha256",
}


def _dry_run_signature_size(kms_signer: AwsKmsSigner) -> int:
    """Return the maximum signature size for the KMS signing algorithm.

    pyHanko invokes ``async_sign_raw`` with ``dry_run=True`` to budget
    the ``/Contents`` placeholder in the PDF. We return a worst-case
    size so the real signature always fits.
    """
    algorithm = kms_signer.algorithm()
    if algorithm == "RSASSA_PSS_SHA256":
        # KMS uses the key's modulus length; TrustSeal's documented
        # keys are RSA 2048 or 3072. 384 bytes covers 3072, 256 covers
        # 2048; pick the larger so a key rotation to 3072 does not
        # retroactively invalidate dry-run budgeting.
        return 384
    if algorithm == "ECDSA_SHA256":
        # P-256 ECDSA DER-encoded signatures are at most 72 bytes.
        return 72
    raise AlgorithmUnsupported(f"Unsupported KMS algorithm: {algorithm}")


def _signature_mechanism(kms_signer: AwsKmsSigner) -> asn_algos.SignedDigestAlgorithm:
    """Return the ASN.1 mechanism identifier for pyHanko's CMS output."""
    algorithm = kms_signer.algorithm()
    if algorithm == "RSASSA_PSS_SHA256":
        # RSASSA-PSS with MGF1-SHA256 and 32-byte salt matches KMS
        # output. See KMS asymmetric signing algorithm reference.
        return asn_algos.SignedDigestAlgorithm(
            {
                "algorithm": "rsassa_pss",
                "parameters": asn_algos.RSASSAPSSParams(
                    {
                        "hash_algorithm": asn_algos.DigestAlgorithm(
                            {"algorithm": "sha256"}
                        ),
                        "mask_gen_algorithm": asn_algos.MaskGenAlgorithm(
                            {
                                "algorithm": "mgf1",
                                "parameters": asn_algos.DigestAlgorithm(
                                    {"algorithm": "sha256"}
                                ),
                            }
                        ),
                        "salt_length": 32,
                        "trailer_field": 1,
                    }
                ),
            }
        )
    if algorithm == "ECDSA_SHA256":
        return asn_algos.SignedDigestAlgorithm({"algorithm": "sha256_ecdsa"})
    raise AlgorithmUnsupported(f"Unsupported KMS algorithm: {algorithm}")


class KmsPyhankoSigner(ExternalSigner):
    """``ExternalSigner`` whose ``async_sign_raw`` calls AWS KMS.

    Instances are stateless beyond the KMS client; one signer may be
    reused across many sealing operations. A dedicated signer should
    be constructed per request if any per-request parameter (e.g.
    operator identity, correlation id) needs to appear in the request
    tags sent to KMS.
    """

    def __init__(
        self,
        kms_signer: AwsKmsSigner,
        signing_cert: asn_x509.Certificate,
        extra_certs: Iterable[asn_x509.Certificate] = (),
    ) -> None:
        store = SimpleCertificateStore()
        for cert in extra_certs:
            store.register(cert)
        super().__init__(
            signing_cert=signing_cert,
            cert_registry=store,
            signature_value=_dry_run_signature_size(kms_signer),
            signature_mechanism=_signature_mechanism(kms_signer),
            prefer_pss=(kms_signer.algorithm() == "RSASSA_PSS_SHA256"),
            embed_roots=True,
        )
        self._kms_signer = kms_signer

    async def async_sign_raw(
        self,
        data: bytes,
        digest_algorithm: str,
        dry_run: bool = False,
    ) -> bytes:
        if dry_run:
            # pyHanko only needs to know the size budget. Returning
            # zero bytes works because ``signature_value`` was passed
            # as an int to ``ExternalSigner`` above, which pyHanko
            # interprets as the dry-run budget.
            return b"\x00" * _dry_run_signature_size(self._kms_signer)
        expected = _DIGEST_FOR_ALGORITHM.get(self._kms_signer.algorithm())
        if digest_algorithm != expected:
            raise SignerError(
                f"KMS signer configured for {expected}, got {digest_algorithm}"
            )
        envelope = self._kms_signer.sign(data)
        return envelope.signature


def _load_cert(path: str, label: str) -> asn_x509.Certificate:
    import os

    if not isinstance(path, str) or not os.path.isabs(path):
        raise SignerError(f"{label} requires an absolute PEM path")
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise SignerError(f"{label} is not a readable PEM file")
    pem = candidate.read_bytes()
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization as cs

    cert = x509.load_pem_x509_certificate(pem)  # validates PEM
    return asn_x509.Certificate.load(cert.public_bytes(cs.Encoding.DER))


def build_kms_pyhanko_signer(
    *,
    key_id: str,
    cert_pem_path: str,
    extra_certs_pem_paths: Iterable[str] = (),
    signing_algorithm: str = "RSASSA_PSS_SHA_256",
    region: str | None = None,
    kms_client=None,
) -> KmsPyhankoSigner:
    """Construct an :class:`KmsPyhankoSigner` from configuration paths."""
    kms_signer = AwsKmsSigner(
        key_id=key_id,
        signing_algorithm=signing_algorithm,
        region=region,
        client=kms_client,
    )
    cert = _load_cert(cert_pem_path, "Platform signing certificate")
    extras = [_load_cert(p, "Chain certificate") for p in extra_certs_pem_paths]
    return KmsPyhankoSigner(kms_signer, cert, extras)
