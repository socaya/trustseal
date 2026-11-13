"""Bounded explicit X.509 path verification for the configured TSA signer.

This checks signatures, CA authority, time, algorithms and common constraints
for a fixed root-to-leaf chain. It is NOT a complete RFC 5280 path engine:
name constraints, policies, full critical extension semantics, historical
trust-list status and chain-wide revocation remain unverified.
"""
import base64
import hashlib
import json
from datetime import timezone

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtensionOID, ExtendedKeyUsageOID

from app.services.certificate_revocation import _read_pem, _verify_signature

MAX_INTERMEDIATES = 4
MAX_CHAIN_CERT = 32768
ALLOWED_SIGNATURE_HASHES = {"sha256", "sha384", "sha512"}


class ChainValidationError(ValueError):
    pass


def _date(value):
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _read_certificate(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_CHAIN_CERT:
        raise ChainValidationError("Unbounded certificate input")
    try:
        return x509.load_pem_x509_certificate(raw)
    except (ValueError, TypeError) as exc:
        raise ChainValidationError("Unsupported X.509 certificate encoding") from exc


def _fingerprint(certificate):
    return hashlib.sha256(
        certificate.public_bytes(serialization.Encoding.DER)
    ).hexdigest()


def _extension(cert, oid, label):
    try:
        return cert.extensions.get_extension_for_oid(oid).value
    except x509.ExtensionNotFound as exc:
        raise ChainValidationError(label + " missing required certificate extension") from exc


def _key_identifier(child, issuer):
    try:
        aki = child.extensions.get_extension_for_oid(
            ExtensionOID.AUTHORITY_KEY_IDENTIFIER
        ).value
    except x509.ExtensionNotFound:
        return
    if aki.key_identifier is not None:
        try:
            ski = issuer.extensions.get_extension_for_oid(
                ExtensionOID.SUBJECT_KEY_IDENTIFIER
            ).value.digest
        except x509.ExtensionNotFound as exc:
            raise ChainValidationError("Issuer SKI required to verify AKI") from exc
        if aki.key_identifier != ski:
            raise ChainValidationError("Authority key identity mismatch")
    if aki.authority_cert_serial_number is not None:
        if aki.authority_cert_serial_number != issuer.serial_number:
            raise ChainValidationError("Authority certificate serial mismatch")
    if aki.authority_cert_issuer is not None:
        names = [x.value for x in aki.authority_cert_issuer
                 if isinstance(x, x509.DirectoryName)]
        if names and issuer.issuer not in names:
            raise ChainValidationError("Authority issuer identity mismatch")


def _check_signature(cert, issuer):
    if cert.issuer != issuer.subject:
        raise ChainValidationError("Certificate issuer/subject discontinuity")
    digest = cert.signature_hash_algorithm
    if digest is not None and digest.name.lower() not in ALLOWED_SIGNATURE_HASHES:
        raise ChainValidationError("Unapproved certificate signature hash")
    _key_identifier(cert, issuer)
    try:
        _verify_signature(
            issuer.public_key(), cert.signature,
            cert.tbs_certificate_bytes, digest,
        )
    except Exception as exc:
        raise ChainValidationError("Certificate signature invalid") from exc


def validate_explicit_chain(leaf_pem, intermediate_pems, root_pem, at):
    if not isinstance(intermediate_pems, (list, tuple)) or len(intermediate_pems) > MAX_INTERMEDIATES:
        raise ChainValidationError("Certificate chain exceeds policy limits")
    leaf = _read_certificate(leaf_pem)
    intermediates = [_read_certificate(blob) for blob in intermediate_pems]
    root = _read_certificate(root_pem)
    chain = [leaf, *intermediates, root]
    fingerprints = [_fingerprint(cert) for cert in chain]
    if len(set(fingerprints)) != len(chain):
        raise ChainValidationError("Duplicate or cyclic certificate chain")
    if root.subject != root.issuer:
        raise ChainValidationError("Pinned trust root must be self-issued")
    observed = _date(at)
    for cert in chain:
        begin = _date(getattr(cert, "not_valid_before_utc", None) or cert.not_valid_before)
        end = _date(getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after)
        if not begin <= observed <= end:
            raise ChainValidationError("Certificate outside historical validity interval")
    for child, issuer in zip(chain, chain[1:]):
        _check_signature(child, issuer)
    _check_signature(root, root)
    for position, issuer in enumerate(chain[1:], start=1):
        constraints = _extension(issuer, ExtensionOID.BASIC_CONSTRAINTS, "Issuer CA constraints")
        usage = _extension(issuer, ExtensionOID.KEY_USAGE, "Issuer key usage")
        if not constraints.ca or not usage.key_cert_sign:
            raise ChainValidationError("Certificate issuer lacks CA authority")
        subordinate_cas = sum(
            1 for cert in chain[1:position] if _extension(
                cert, ExtensionOID.BASIC_CONSTRAINTS, "Intermediate CA constraints"
            ).ca and cert.subject != cert.issuer
        )
        if constraints.path_length is not None and subordinate_cas > constraints.path_length:
            raise ChainValidationError("Issuer path length constraint exceeded")
    tsa_eku = _extension(leaf, ExtensionOID.EXTENDED_KEY_USAGE, "TSA EKU")
    if ExtendedKeyUsageOID.TIME_STAMPING not in tsa_eku:
        raise ChainValidationError("Leaf certificate not authorized for timestamp signing")
    leaf_usage = _extension(leaf, ExtensionOID.KEY_USAGE, "TSA key usage")
    leaf_ca = _extension(leaf, ExtensionOID.BASIC_CONSTRAINTS, "TSA CA constraints")
    if leaf_ca.ca or not leaf_usage.digital_signature or not leaf_usage.content_commitment:
        raise ChainValidationError("Leaf certificate not a signing-only TSA certificate")
    return {
        "schema": "trustseal.explicit-tsa-chain.v1",
        "assurance": "bounded_explicit_certificate_path_not_full_rfc5280",
        "complete_pkix_validation": False,
        "validation_time": observed.isoformat(timespec="microseconds") + "Z",
        "leaf_sha256": fingerprints[0],
        "root_sha256": fingerprints[-1],
        "certificates_sha256_leaf_to_root": fingerprints,
        "certificates_der_b64_leaf_to_root": [
            base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode("ascii")
            for cert in chain
        ],
        "revocation_verified_for_entire_chain": False,
    }


def chain_from_config(config, at):
    leaf = config.get("RFC3161_TSA_CERT_PEM")
    root = config.get("RFC3161_TRUST_ROOT_PEM")
    if not leaf or not root:
        return None
    intermediate = config.get("VALIDATION_TSA_INTERMEDIATES_JSON") or "[]"
    try:
        paths = json.loads(intermediate)
    except (ValueError, TypeError) as exc:
        raise ChainValidationError("Invalid configured intermediate certificates") from exc
    if (not isinstance(paths, list) or len(paths) > MAX_INTERMEDIATES
            or any(not isinstance(path, str) for path in paths)):
        raise ChainValidationError("Invalid intermediate certificate list")
    result = validate_explicit_chain(
        _read_pem(leaf, "TSA leaf"),
        [_read_pem(path, "TSA intermediate") for path in paths],
        _read_pem(root, "TSA root"),
        at,
    )
    return result
