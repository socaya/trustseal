"""Factory for detached-signature signers.

Platform PDF sealing (``PDF_PLATFORM_*``) stays with its historical
PKCS#12 bootstrap because pyHanko's ``ExternalSigner`` integration lives
in a dedicated migration ticket. For detached JSON evidence (review
receipts, evidence checkpoints, stamp attestations) the factory selects
the backend declared by ``RECEIPT_SIGNER_BACKEND``.
"""
from __future__ import annotations

from typing import Any

from .aws_kms import AwsKmsSigner
from .base import Signer, SignerError
from .local_ed25519 import LocalEd25519Signer


def build_detached_signer(config: Any) -> Signer:
    backend = (config.get("RECEIPT_SIGNER_BACKEND") or "local_ed25519").strip().lower()
    if backend == "local_ed25519":
        path = config.get("REVIEW_RECEIPT_PRIVATE_KEY")
        if not path:
            raise SignerError(
                "REVIEW_RECEIPT_PRIVATE_KEY required for local_ed25519 signer"
            )
        return LocalEd25519Signer(path)
    if backend == "aws_kms":
        key_id = config.get("RECEIPT_SIGNER_KMS_KEY_ID")
        algorithm = config.get("RECEIPT_SIGNER_KMS_ALGORITHM", "RSASSA_PSS_SHA_256")
        region = config.get("RECEIPT_SIGNER_KMS_REGION")
        if not key_id:
            raise SignerError(
                "RECEIPT_SIGNER_KMS_KEY_ID required for aws_kms signer"
            )
        return AwsKmsSigner(key_id=key_id, signing_algorithm=algorithm, region=region)
    raise SignerError(
        f"Unknown RECEIPT_SIGNER_BACKEND {backend!r}; expected local_ed25519, aws_kms"
    )
