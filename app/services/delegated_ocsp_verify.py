"""Standalone verification of a delegated OCSP responder certificate.

The existing ``ocsp_evidence`` module already runs these checks
inline when validating a signed OCSP response. Extracting the logic
into a dedicated service lets callers:

* Validate an operator-supplied responder certificate *before*
  accepting it as a trusted OCSP signer (e.g. at
  provisioning time).
* Write unit tests against a known-good responder + a battery of
  adversarial ones.
* Document the exact security properties being enforced in one
  place that compliance reviewers can audit.

Checks (any failure raises :class:`DelegatedResponderError`):

1. The responder was signed by the supplied issuer (i.e. the CA
   that signs the leaf certificates whose status the responder
   reports on).
2. The responder carries the ``id-kp-OCSPSigning`` extended key
   usage OID.
3. The responder carries ``KeyUsage.digital_signature``.
4. The ``now`` moment (default ``datetime.utcnow()``) is within
   the responder's validity window.

The function does NOT fetch certificates over the network or
touch revocation state — those are the caller's responsibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509 import ExtensionNotFound
from cryptography.x509.oid import ExtendedKeyUsageOID, ExtensionOID


class DelegatedResponderError(RuntimeError):
    """Raised when a delegated responder cert fails verification."""


@dataclass(frozen=True)
class ResponderCheck:
    responder_serial: int
    issuer_serial: int
    not_before: datetime
    not_after: datetime


def verify_responder_certificate(
    responder_cert: x509.Certificate,
    issuer_cert: x509.Certificate,
    *,
    now: Optional[datetime] = None,
) -> ResponderCheck:
    """Validate ``responder_cert`` against the ``issuer_cert``.

    See the module docstring for the enforced checks. Returns a
    :class:`ResponderCheck` describing the certificate on success.
    """
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    if responder_cert.issuer != issuer_cert.subject:
        raise DelegatedResponderError(
            "responder_not_issued_by_supplied_issuer"
        )
    public_key = issuer_cert.public_key()
    try:
        # RSA + ECDSA both supported by cryptography's verify API via
        # algorithm selection. Try RSA PKCS1v15 first (OCSP responders
        # overwhelmingly use it); fall back to ECDSA.
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
        from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey

        if isinstance(public_key, RSAPublicKey):
            public_key.verify(
                responder_cert.signature,
                responder_cert.tbs_certificate_bytes,
                padding.PKCS1v15(),
                responder_cert.signature_hash_algorithm,
            )
        elif isinstance(public_key, EllipticCurvePublicKey):
            from cryptography.hazmat.primitives.asymmetric import ec

            public_key.verify(
                responder_cert.signature,
                responder_cert.tbs_certificate_bytes,
                ec.ECDSA(responder_cert.signature_hash_algorithm),
            )
        else:
            raise DelegatedResponderError(
                "unsupported_issuer_key_type"
            )
    except InvalidSignature as exc:
        raise DelegatedResponderError(
            "responder_signature_invalid"
        ) from exc
    # Validity window.
    not_before = responder_cert.not_valid_before_utc
    not_after = responder_cert.not_valid_after_utc
    if moment < not_before:
        raise DelegatedResponderError("responder_not_yet_valid")
    if moment > not_after:
        raise DelegatedResponderError("responder_expired")
    # EKU.
    try:
        eku = responder_cert.extensions.get_extension_for_oid(
            ExtensionOID.EXTENDED_KEY_USAGE
        ).value
    except ExtensionNotFound as exc:
        raise DelegatedResponderError(
            "responder_missing_eku"
        ) from exc
    if ExtendedKeyUsageOID.OCSP_SIGNING not in eku:
        raise DelegatedResponderError(
            "responder_lacks_ocsp_signing_eku"
        )
    # KeyUsage.
    try:
        ku = responder_cert.extensions.get_extension_for_oid(
            ExtensionOID.KEY_USAGE
        ).value
    except ExtensionNotFound as exc:
        raise DelegatedResponderError(
            "responder_missing_key_usage"
        ) from exc
    if not ku.digital_signature:
        raise DelegatedResponderError(
            "responder_key_usage_lacks_digital_signature"
        )
    return ResponderCheck(
        responder_serial=responder_cert.serial_number,
        issuer_serial=issuer_cert.serial_number,
        not_before=not_before,
        not_after=not_after,
    )
