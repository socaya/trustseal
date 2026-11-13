"""Strict offline X.509 CRL validation with issuer and subject pinning.

CRL signature, validity window, issuer eligibility, trust anchor, and subject
certificate binding are mandatory. CRL 'good' means *not listed on that CRL*,
not an independent proof of good standing at an arbitrary historical time.
No network fetch or automatic status inference is performed.
"""
import base64
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, ed448, padding, rsa
from cryptography.x509.oid import ExtensionOID


MAX_CRL = 512 * 1024
MAX_CERT = 32 * 1024


class RevocationEvidenceError(ValueError):
    pass


def _utc_naive(dt):
    if dt is None:
        raise RevocationEvidenceError("Revocation validity interval incomplete")
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _verify_signature(public, signature, message, algorithm):
    try:
        if isinstance(public, rsa.RSAPublicKey):
            public.verify(signature, message, padding.PKCS1v15(), algorithm)
        elif isinstance(public, ec.EllipticCurvePublicKey):
            public.verify(signature, message, ec.ECDSA(algorithm))
        elif isinstance(public, (ed25519.Ed25519PublicKey, ed448.Ed448PublicKey)):
            public.verify(signature, message)
        else:
            raise RevocationEvidenceError("Unsupported CRL issuer key")
    except RevocationEvidenceError:
        raise
    except Exception as exc:
        raise RevocationEvidenceError("Certificate or CRL signature invalid") from exc


def _read_pem(path, label):
    if not isinstance(path, str) or not os.path.isabs(path):
        raise RevocationEvidenceError(label + " must be an absolute path")
    file = Path(path)
    if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_CERT:
        raise RevocationEvidenceError(label + " is not an approved certificate file")
    return file.read_bytes()


def validate_crl(crl_bytes, subject_pem, issuer_pem, root_pem, *, observed_at=None):
    if not isinstance(crl_bytes, bytes) or not 0 < len(crl_bytes) <= MAX_CRL:
        raise RevocationEvidenceError("CRL exceeds size limit")
    if any(not isinstance(p, bytes) or len(p) > MAX_CERT for p in (subject_pem, issuer_pem, root_pem)):
        raise RevocationEvidenceError("Certificate size invalid")
    try:
        crl = x509.load_der_x509_crl(crl_bytes)
        subject = x509.load_pem_x509_certificate(subject_pem)
        issuer = x509.load_pem_x509_certificate(issuer_pem)
        root = x509.load_pem_x509_certificate(root_pem)
    except (ValueError, TypeError) as exc:
        raise RevocationEvidenceError("Invalid certificate or CRL encoding") from exc

    if crl.issuer != issuer.subject or subject.issuer != issuer.subject:
        raise RevocationEvidenceError("CRL issuer does not match certificate issuer")
    if issuer.issuer != root.subject:
        raise RevocationEvidenceError("Issuer must be directly signed by pinned root")
    if issuer.subject != root.subject or issuer.serial_number != root.serial_number:
        _verify_signature(root.public_key(), issuer.signature, issuer.tbs_certificate_bytes,
                          issuer.signature_hash_algorithm)
    elif issuer.public_bytes(serialization.Encoding.DER) != root.public_bytes(serialization.Encoding.DER):
        raise RevocationEvidenceError("Root certificate substitution detected")
    else:
        _verify_signature(root.public_key(), root.signature, root.tbs_certificate_bytes,
                          root.signature_hash_algorithm)

    try:
        issuer_usage = issuer.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE).value
        issuer_ca = issuer.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS).value
        if not issuer_usage.crl_sign or not issuer_usage.key_cert_sign or not issuer_ca.ca:
            raise RevocationEvidenceError("CRL issuer lacks CA and CRL signing authority")
    except x509.ExtensionNotFound as exc:
        raise RevocationEvidenceError("Issuer certificate lacks key usage constraints") from exc

    _verify_signature(issuer.public_key(), subject.signature,
                      subject.tbs_certificate_bytes, subject.signature_hash_algorithm)
    _verify_signature(issuer.public_key(), crl.signature,
                      crl.tbs_certlist_bytes, crl.signature_hash_algorithm)
    this_update = _utc_naive(getattr(crl, "last_update_utc", None) or crl.last_update)
    next_update = _utc_naive(getattr(crl, "next_update_utc", None) or crl.next_update)
    checked = observed_at or datetime.utcnow()
    checked = _utc_naive(checked)
    if not (this_update <= checked < next_update):
        raise RevocationEvidenceError("CRL not valid at observation time")
    if next_update <= this_update:
        raise RevocationEvidenceError("CRL time window invalid")
    for certificate, purpose in ((root, "Trusted root"),
                                 (issuer, "CRL issuer"),
                                 (subject, "TSA signer")):
        if not (_utc_naive(getattr(certificate, "not_valid_before_utc", None)
                           or certificate.not_valid_before)
                <= checked <= _utc_naive(getattr(certificate, "not_valid_after_utc", None)
                                         or certificate.not_valid_after)):
            raise RevocationEvidenceError(purpose + " certificate outside validity interval")
    # Where the CRL declares the key of its issuer, prohibit substituting
    # a different CA certificate with the same name.
    try:
        crl_aki = crl.extensions.get_extension_for_oid(
            ExtensionOID.AUTHORITY_KEY_IDENTIFIER
        ).value.key_identifier
        issuer_ski = issuer.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_KEY_IDENTIFIER
        ).value.digest
        if crl_aki is not None and crl_aki != issuer_ski:
            raise RevocationEvidenceError("CRL authority key identifier mismatch")
    except x509.ExtensionNotFound:
        pass
    revoked = crl.get_revoked_certificate_by_serial_number(subject.serial_number)
    return {
        "subject_certificate_sha256": hashlib.sha256(subject.public_bytes(serialization.Encoding.DER)).hexdigest(),
        "issuer_certificate_sha256": hashlib.sha256(issuer.public_bytes(serialization.Encoding.DER)).hexdigest(),
        "crl_sha256": hashlib.sha256(crl_bytes).hexdigest(),
        "status": "revoked" if revoked is not None else "good",
        "this_update": this_update,
        "next_update": next_update,
        "checked_at": checked,
    }


def verify_snapshot(record, root_pem, *, require_current=False):
    try:
        crl = base64.b64decode(record.crl_der_b64, validate=True)
        subject = base64.b64decode(record.subject_der_b64, validate=True)
        issuer = base64.b64decode(record.issuer_der_b64, validate=True)
        subject_cert = x509.load_der_x509_certificate(subject)
        issuer_cert = x509.load_der_x509_certificate(issuer)
        observed = record.checked_at
        result = validate_crl(
            crl,
            subject_cert.public_bytes(serialization.Encoding.PEM),
            issuer_cert.public_bytes(serialization.Encoding.PEM),
            root_pem,
            observed_at=observed,
        )
        if any(result[field] != getattr(record, field) for field in (
            "subject_certificate_sha256", "issuer_certificate_sha256",
            "crl_sha256", "status", "this_update", "next_update",
        )):
            raise RevocationEvidenceError("Stored revocation evidence altered")
        if require_current and not result["this_update"] <= datetime.utcnow() < result["next_update"]:
            raise RevocationEvidenceError("CRL status snapshot expired")
        return result
    except (ValueError, TypeError, KeyError) as exc:
        raise RevocationEvidenceError("CRL snapshot validation failed") from exc
