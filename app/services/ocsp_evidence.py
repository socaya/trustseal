"""Fail-closed offline OCSP verifier for an issuer-signed TSA leaf response.

No network fetch, delegated responder trust, or unverified status inference.
The exact single-response CertID is matched to a generated OCSP request.
"""
import base64
import hashlib
from datetime import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509 import ocsp
from cryptography.x509.oid import ExtensionOID, ExtendedKeyUsageOID
from asn1crypto import keys

from app.services.certificate_revocation import (
    RevocationEvidenceError, _utc_naive, _verify_signature,
)

MAX_OCSP = 128 * 1024
MAX_CERT = 32 * 1024


class OcspEvidenceError(ValueError):
    pass


def _sha256(cert):
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def _load_cert(data):
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_CERT:
        raise OcspEvidenceError("Invalid certificate bytes")
    try:
        return x509.load_pem_x509_certificate(data)
    except ValueError as exc:
        raise OcspEvidenceError("Invalid PEM certificate") from exc


def _responder_key_hash(certificate):
    spki = keys.PublicKeyInfo.load(
        certificate.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    return hashlib.sha1(spki["public_key"].contents[1:]).digest()


def _responder_certificate(response, issuer):
    """Resolve the exact OCSP signer, never trusting arbitrary embedded certs."""
    candidates = [issuer, *response.certificates]
    matched = []
    for certificate in candidates:
        if (response.responder_name is not None and response.responder_name == certificate.subject
                or response.responder_key_hash is not None
                and response.responder_key_hash == _responder_key_hash(certificate)):
            if all(_sha256(certificate) != _sha256(old) for old in matched):
                matched.append(certificate)
    if len(matched) != 1:
        raise OcspEvidenceError("OCSP signer is absent or ambiguous")
    return matched[0]


def validate_ocsp(response_der, subject_pem, issuer_pem, root_pem, *,
                  observed_at=None, expected_responder_der=None):
    if not isinstance(response_der, bytes) or not 0 < len(response_der) <= MAX_OCSP:
        raise OcspEvidenceError("OCSP response size exceeds limit")
    try:
        subject, issuer, root = (_load_cert(p) for p in (subject_pem, issuer_pem, root_pem))
        response = ocsp.load_der_ocsp_response(response_der)
        if response.response_status != ocsp.OCSPResponseStatus.SUCCESSFUL:
            raise OcspEvidenceError("OCSP responder did not return successful status")
        if subject.issuer != issuer.subject or issuer.issuer != root.subject:
            raise OcspEvidenceError("OCSP certificate issuer or root mismatch")
        if issuer.public_bytes(serialization.Encoding.DER) == root.public_bytes(serialization.Encoding.DER):
            _verify_signature(root.public_key(), root.signature, root.tbs_certificate_bytes,
                              root.signature_hash_algorithm)
        else:
            _verify_signature(root.public_key(), issuer.signature,
                              issuer.tbs_certificate_bytes, issuer.signature_hash_algorithm)
        try:
            constraints = issuer.extensions.get_extension_for_oid(
                ExtensionOID.BASIC_CONSTRAINTS
            ).value
            usage = issuer.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE).value
            if not constraints.ca or not usage.key_cert_sign:
                raise OcspEvidenceError("OCSP issuer is not an authorized CA")
        except x509.ExtensionNotFound as exc:
            raise OcspEvidenceError("OCSP issuer CA restrictions are absent") from exc
        _verify_signature(issuer.public_key(), subject.signature,
                          subject.tbs_certificate_bytes, subject.signature_hash_algorithm)
        # This intentionally supports only directly CA-signed OCSP status,
        # not delegated responders with separately validated OCSPSigning EKU.
        expected = ocsp.OCSPRequestBuilder().add_certificate(
            subject, issuer, hashes.SHA256()
        ).build()
        if (response.serial_number != expected.serial_number
                or response.issuer_name_hash != expected.issuer_name_hash
                or response.issuer_key_hash != expected.issuer_key_hash
                or response.hash_algorithm.name != "sha256"):
            raise OcspEvidenceError("OCSP CertID differs from pinned certificate")
        signer = _responder_certificate(response, issuer)
        delegated = _sha256(signer) != _sha256(issuer)
        if delegated:
            if signer.issuer != issuer.subject:
                raise OcspEvidenceError("Delegated responder not issued by certificate authority")
            if all(_sha256(signer) != _sha256(embedded) for embedded in response.certificates):
                raise OcspEvidenceError("Delegated certificate not retained in signed response")
            _verify_signature(
                issuer.public_key(), signer.signature,
                signer.tbs_certificate_bytes, signer.signature_hash_algorithm,
            )
            try:
                eku = signer.extensions.get_extension_for_oid(
                    ExtensionOID.EXTENDED_KEY_USAGE
                ).value
                ku = signer.extensions.get_extension_for_oid(
                    ExtensionOID.KEY_USAGE
                ).value
                if ExtendedKeyUsageOID.OCSP_SIGNING not in eku or not ku.digital_signature:
                    raise OcspEvidenceError("Delegated responder lacks OCSP signing authority")
            except x509.ExtensionNotFound as exc:
                raise OcspEvidenceError("Delegated OCSP signer EKU/key usage required") from exc
            try:
                bc = signer.extensions.get_extension_for_oid(
                    ExtensionOID.BASIC_CONSTRAINTS
                ).value
                if bc.ca:
                    raise OcspEvidenceError("Delegated OCSP responder cannot be a CA")
            except x509.ExtensionNotFound:
                raise OcspEvidenceError("Delegated responder constraints absent") from None
        actual_responder_der = signer.public_bytes(serialization.Encoding.DER)
        if expected_responder_der is not None and actual_responder_der != expected_responder_der:
            raise OcspEvidenceError("Responder certificate differs from retained evidence")
        _verify_signature(
            signer.public_key(), response.signature,
            response.tbs_response_bytes, response.signature_hash_algorithm,
        )
        checked = _utc_naive(observed_at or datetime.utcnow())
        produced = _utc_naive(getattr(response, "produced_at_utc", None) or response.produced_at)
        start = _utc_naive(getattr(response, "this_update_utc", None) or response.this_update)
        end = _utc_naive(getattr(response, "next_update_utc", None) or response.next_update)
        if not (start <= checked < end) or end <= start:
            raise OcspEvidenceError("OCSP response outside validity interval")
        if produced > checked:
            raise OcspEvidenceError("OCSP response claims future production time")
        for certificate in (subject, issuer, root, signer):
            begin = _utc_naive(getattr(certificate, "not_valid_before_utc", None)
                               or certificate.not_valid_before)
            finish = _utc_naive(getattr(certificate, "not_valid_after_utc", None)
                                or certificate.not_valid_after)
            if not begin <= checked <= finish:
                raise OcspEvidenceError("OCSP certificate outside validity interval")
        status = {
            ocsp.OCSPCertStatus.GOOD: "good",
            ocsp.OCSPCertStatus.REVOKED: "revoked",
            ocsp.OCSPCertStatus.UNKNOWN: "unknown",
        }[response.certificate_status]
        return {
            "subject_certificate_sha256": _sha256(subject),
            "issuer_certificate_sha256": _sha256(issuer),
            "response_sha256": hashlib.sha256(response_der).hexdigest(),
            "produced_at": produced, "this_update": start, "next_update": end,
            "checked_at": checked, "status": status,
            "responder_certificate_sha256": _sha256(signer),
            "responder_der_b64": base64.b64encode(actual_responder_der).decode("ascii"),
            "delegated": delegated,
        }
    except OcspEvidenceError:
        raise
    except (RevocationEvidenceError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise OcspEvidenceError("OCSP signature or certificate validation failed") from exc


def verify_ocsp_snapshot(record, root_pem, *, require_current=False):
    try:
        response = base64.b64decode(record.response_der_b64, validate=True)
        subject = x509.load_der_x509_certificate(base64.b64decode(
            record.subject_der_b64, validate=True
        ))
        issuer = x509.load_der_x509_certificate(base64.b64decode(
            record.issuer_der_b64, validate=True
        ))
        stored_responder = getattr(record, "responder_der_b64", None)
        expected_responder = (
            base64.b64decode(stored_responder, validate=True)
            if stored_responder is not None else None
        )
        result = validate_ocsp(
            response,
            subject.public_bytes(serialization.Encoding.PEM),
            issuer.public_bytes(serialization.Encoding.PEM),
            root_pem, observed_at=record.checked_at,
            expected_responder_der=expected_responder,
        )
        stored_sha = getattr(record, "responder_certificate_sha256", None)
        if stored_sha is not None and stored_sha != result["responder_certificate_sha256"]:
            raise OcspEvidenceError("Responder fingerprint changed")
        if stored_responder is None and result["delegated"]:
            raise OcspEvidenceError("Historical delegated responder evidence missing")
        fields = ("subject_certificate_sha256", "issuer_certificate_sha256",
                  "response_sha256", "status", "produced_at",
                  "this_update", "next_update")
        if any(result[key] != getattr(record, key) for key in fields):
            raise OcspEvidenceError("Stored OCSP observation altered")
        if require_current and not result["this_update"] <= datetime.utcnow() < result["next_update"]:
            raise OcspEvidenceError("OCSP observation no longer current")
        return result
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise OcspEvidenceError("OCSP snapshot could not be validated") from exc
