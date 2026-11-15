"""File-backed Ed25519 signer.

Wraps the behaviour :mod:`app.services.signing_receipts` has had since
inception. Adopting the :class:`Signer` interface here lets domain code
depend on a stable abstraction while the key still comes from disk;
nothing in the interface precludes a future KMS-backed Ed25519 once a
vendor supports it.
"""
from __future__ import annotations

import hashlib
import stat
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .base import Signer, SignatureEnvelope, SignerError

ALGORITHM = "Ed25519"


class LocalEd25519Signer(Signer):
    def __init__(self, private_key_path: str) -> None:
        if not isinstance(private_key_path, str) or not Path(private_key_path).is_absolute():
            raise SignerError("Absolute Ed25519 private key path required")
        path = Path(private_key_path)
        if path.is_symlink() or not path.is_file():
            raise SignerError("Protected Ed25519 key file required")
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise SignerError("Ed25519 key must not be group/world accessible")
        try:
            key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        except (ValueError, TypeError) as exc:
            raise SignerError("Invalid Ed25519 PEM") from exc
        if not isinstance(key, Ed25519PrivateKey):
            raise SignerError("PEM is not an Ed25519 private key")
        self._key = key
        raw = key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self._key_id = "ed25519-sha256:" + hashlib.sha256(raw).hexdigest()

    def sign(self, payload: bytes) -> SignatureEnvelope:
        if not isinstance(payload, (bytes, bytearray)):
            raise SignerError("payload must be bytes")
        signature = self._key.sign(bytes(payload))
        return SignatureEnvelope(
            algorithm=ALGORITHM,
            signature=signature,
            key_identifier=self._key_id,
        )

    def key_identifier(self) -> str:
        return self._key_id

    def algorithm(self) -> str:
        return ALGORITHM
