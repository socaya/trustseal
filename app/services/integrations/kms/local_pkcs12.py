"""File-backed PKCS#12 signer.

Thin wrapper around the pre-existing ``_signing_credentials`` helper in
:mod:`app.services.platform_pdf_seal`. Exposes the pyHanko signer via
:attr:`pyhanko_signer` so callers that need the pyHanko-specific
``SimpleSigner`` interface keep working without re-implementing the
PKCS#12 loader.

The :class:`Signer` ``sign`` operation uses the private key to produce a
raw RSASSA-PSS-SHA256 signature of ``payload``. That lets non-PDF use
cases (e.g. detached JSON attestations) reuse the same key material.
"""
from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa, ec
from cryptography.hazmat.primitives.serialization import pkcs12

from .base import AlgorithmUnsupported, Signer, SignatureEnvelope, SignerError


class LocalPkcs12Signer(Signer):
    def __init__(self, path: str, password: str) -> None:
        if not isinstance(path, str) or not os.path.isabs(path):
            raise SignerError("Absolute PKCS#12 path required")
        candidate = Path(path)
        if candidate.is_symlink() or not candidate.is_file():
            raise SignerError("Protected PKCS#12 file required")
        if candidate.stat().st_mode & 0o077:
            raise SignerError("PKCS#12 file must not be group/world accessible")
        if not isinstance(password, str) or not password:
            raise SignerError("PKCS#12 password required")
        self._path = candidate
        self._password = password
        try:
            private_key, cert, _chain = pkcs12.load_key_and_certificates(
                candidate.read_bytes(), password.encode("utf-8")
            )
        except (ValueError, TypeError) as exc:
            raise SignerError("Invalid PKCS#12 bundle") from exc
        if private_key is None or cert is None:
            raise SignerError("PKCS#12 bundle missing key or certificate")
        self._private_key = private_key
        self._cert = cert
        fingerprint = cert.fingerprint(hashes.SHA256()).hex()
        if isinstance(private_key, rsa.RSAPrivateKey):
            self._algorithm = "RSASSA_PSS_SHA256"
        elif isinstance(private_key, ec.EllipticCurvePrivateKey):
            self._algorithm = "ECDSA_SHA256"
        else:
            raise AlgorithmUnsupported("PKCS#12 key type is not supported")
        self._key_id = f"{self._algorithm.lower()}-cert-sha256:{fingerprint}"

    # ----- interface ------------------------------------------------

    def sign(self, payload: bytes) -> SignatureEnvelope:
        if not isinstance(payload, (bytes, bytearray)):
            raise SignerError("payload must be bytes")
        data = bytes(payload)
        if isinstance(self._private_key, rsa.RSAPrivateKey):
            signature = self._private_key.sign(
                data,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
                hashes.SHA256(),
            )
        elif isinstance(self._private_key, ec.EllipticCurvePrivateKey):
            signature = self._private_key.sign(
                data, ec.ECDSA(hashes.SHA256())
            )
        else:  # pragma: no cover — guarded in __init__
            raise AlgorithmUnsupported("Unsupported private-key type")
        return SignatureEnvelope(
            algorithm=self._algorithm,
            signature=signature,
            key_identifier=self._key_id,
        )

    def key_identifier(self) -> str:
        return self._key_id

    def algorithm(self) -> str:
        return self._algorithm

    # ----- PKCS#12-specific helpers ---------------------------------

    @property
    def path(self) -> Path:
        return self._path

    @property
    def password(self) -> str:
        return self._password

    @property
    def certificate_fingerprint(self) -> str:
        return self._cert.fingerprint(hashes.SHA256()).hex()

    def public_certificate_pem(self) -> bytes:
        return self._cert.public_bytes(serialization.Encoding.PEM)

    def pyhanko_signer(self):
        """Return a pyHanko ``SimpleSigner`` backed by the same PKCS#12.

        Imported lazily so the module stays importable without the
        pyHanko extras installed.
        """
        from pyhanko.sign import signers  # local import

        signer = signers.SimpleSigner.load_pkcs12(
            str(self._path), passphrase=self._password.encode("utf-8")
        )
        if signer is None:
            raise SignerError("pyHanko refused the PKCS#12 bundle")
        return signer
