"""AWS KMS asymmetric signer.

The private key never enters the Python process. Each :meth:`sign` call
issues one ``kms:Sign`` request and returns the raw signature bytes.

Supports the KMS key specs that make sense for TrustSeal:

* ``RSA_2048``, ``RSA_3072``, ``RSA_4096`` with ``RSASSA_PSS_SHA_256``.
* ``ECC_NIST_P256`` with ``ECDSA_SHA_256``.

Ed25519 is not supported by KMS at the time of writing; use
:class:`LocalEd25519Signer` for those keys.

Tests run against moto's in-process KMS mock. No AWS credentials and no
network access are required.
"""
from __future__ import annotations

import hashlib

from .base import AlgorithmUnsupported, Signer, SignatureEnvelope, SignerError

_ALGORITHMS = {
    "RSASSA_PSS_SHA_256": "RSASSA_PSS_SHA256",
    "ECDSA_SHA_256": "ECDSA_SHA256",
}


class AwsKmsSigner(Signer):
    def __init__(
        self,
        key_id: str,
        *,
        signing_algorithm: str = "RSASSA_PSS_SHA_256",
        region: str | None = None,
        client=None,
    ) -> None:
        if not isinstance(key_id, str) or not key_id:
            raise SignerError("KMS key id/ARN required")
        if signing_algorithm not in _ALGORITHMS:
            raise AlgorithmUnsupported(
                f"Unsupported KMS signing algorithm: {signing_algorithm!r}"
            )
        self._key_id = key_id
        self._kms_algorithm = signing_algorithm
        self._canonical_algorithm = _ALGORITHMS[signing_algorithm]
        if client is None:
            import boto3  # local import for optional dependency

            client = boto3.client("kms", region_name=region)
        self._kms = client

    def sign(self, payload: bytes) -> SignatureEnvelope:
        if not isinstance(payload, (bytes, bytearray)):
            raise SignerError("payload must be bytes")
        data = bytes(payload)
        # ``DIGEST`` message type keeps the request body bounded; we
        # hash client-side so the KMS call is small even for large
        # payloads.
        digest = hashlib.sha256(data).digest()
        try:
            response = self._kms.sign(
                KeyId=self._key_id,
                Message=digest,
                MessageType="DIGEST",
                SigningAlgorithm=self._kms_algorithm,
            )
        except Exception as exc:
            raise SignerError(f"KMS sign failed: {exc}") from exc
        signature = response.get("Signature")
        if not isinstance(signature, (bytes, bytearray)):
            raise SignerError("KMS response did not include a signature")
        return SignatureEnvelope(
            algorithm=self._canonical_algorithm,
            signature=bytes(signature),
            key_identifier=self._key_id,
        )

    def key_identifier(self) -> str:
        return self._key_id

    def algorithm(self) -> str:
        return self._canonical_algorithm

    def public_key_der(self) -> bytes:
        """Fetch the KMS key's public key material (SPKI DER)."""
        try:
            response = self._kms.get_public_key(KeyId=self._key_id)
        except Exception as exc:
            raise SignerError(f"KMS get_public_key failed: {exc}") from exc
        public_key = response.get("PublicKey")
        if not isinstance(public_key, (bytes, bytearray)):
            raise SignerError("KMS did not return public-key material")
        return bytes(public_key)
