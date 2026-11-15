"""Signer interface shared by every backend.

Keep the surface small — every method here must have a well-defined
semantic across local file keys, file PKCS#12, and AWS KMS. Methods
that make sense for one backend only (e.g. ``load_pkcs12_path``) live
on the concrete class, never on :class:`Signer`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class SignerError(Exception):
    """Transport-level signer failure (missing key, KMS 4xx/5xx, bad input)."""


class AlgorithmUnsupported(SignerError):
    """Requested algorithm not supported by the backend."""


@dataclass(frozen=True)
class SignatureEnvelope:
    """Opaque result of :meth:`Signer.sign`.

    * ``algorithm`` — canonical algorithm identifier
      (``"Ed25519"``, ``"RSASSA_PSS_SHA256"``, ``"ECDSA_SHA256"``).
    * ``signature`` — raw signature bytes. Base64 encoding is the
      caller's responsibility.
    * ``key_identifier`` — stable identifier for the signing key. For
      local keys this is the ``SHA256`` fingerprint prefixed by the
      algorithm; for AWS KMS it is the key ARN.
    """

    algorithm: str
    signature: bytes
    key_identifier: str


class Signer(ABC):
    @abstractmethod
    def sign(self, payload: bytes) -> SignatureEnvelope:
        ...

    @abstractmethod
    def key_identifier(self) -> str:
        ...

    @abstractmethod
    def algorithm(self) -> str:
        ...
