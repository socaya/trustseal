"""Pluggable signing abstractions.

See ADR 0001. Three implementations ship today:

* :class:`LocalPkcs12Signer` — loads a PKCS#12 key from disk. Used by the
  current platform PDF seal flow and preserves the historic behaviour.
* :class:`LocalEd25519Signer` — loads an Ed25519 key from disk. Used by
  review receipts, evidence checkpoints, and stamp attestations.
* :class:`AwsKmsSigner` — delegates signing to AWS KMS without ever
  exposing the private key to the Python process. Supports RSA_PSS_SHA_256
  and ECDSA_SHA_256 KMS key specs.

All three expose the same narrow :class:`Signer` interface:

    signer.sign(payload: bytes) -> SignatureEnvelope
    signer.key_identifier() -> str

The pyHanko ``ExternalSigner`` plumbing that wires an :class:`AwsKmsSigner`
into the platform PDF seal flow is a separate adapter and ships in a
follow-up ticket (see ``docs/decisions/0001-key-rotation.md``). The
interface here is production-grade and moto-tested.
"""
from .base import (
    Signer,
    SignatureEnvelope,
    SignerError,
    AlgorithmUnsupported,
)
from .factory import build_detached_signer
from .local_pkcs12 import LocalPkcs12Signer
from .local_ed25519 import LocalEd25519Signer
from .aws_kms import AwsKmsSigner
from .pyhanko_external import KmsPyhankoSigner, build_kms_pyhanko_signer

__all__ = [
    "Signer",
    "SignatureEnvelope",
    "SignerError",
    "AlgorithmUnsupported",
    "LocalPkcs12Signer",
    "LocalEd25519Signer",
    "AwsKmsSigner",
    "KmsPyhankoSigner",
    "build_detached_signer",
    "build_kms_pyhanko_signer",
]
