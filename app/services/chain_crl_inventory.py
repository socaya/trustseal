"""Offline issuer-signed CRL evidence for every non-root TSA path certificate.

CRLs are operator supplied, never fetched from certificate URLs. A missing
CRL is reported as missing, not interpreted as a positive certificate status.
This does not implement complete PKIX path processing, historical trust lists,
delta CRLs, indirect CRLs, delegated responders or PAdES-LT/LTA.
"""
import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtensionOID
from app.services.certificate_revocation import _verify_signature
from app.services.explicit_certificate_chain import ChainValidationError, MAX_INTERMEDIATES

MAX_CRL_BYTES = 512 * 1024


def _time(dt):
    if dt is None:
        raise ChainValidationError("CRL nextUpdate is required")
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _certificates(chain_manifest):
    encoded = chain_manifest.get("certificates_der_b64_leaf_to_root")
    if not isinstance(encoded, list) or not 2 <= len(encoded) <= MAX_INTERMEDIATES + 2:
        raise ChainValidationError("Retained TSA certificate path missing")
    certificates = []
    for item in encoded:
        try:
            if not isinstance(item, str) or len(item) > 46000:
                raise ValueError("Invalid certificate size")
            data = base64.b64decode(item, validate=True)
            if not 0 < len(data) <= 32768:
                raise ValueError("Invalid DER certificate size")
            certificates.append(x509.load_der_x509_certificate(data))
        except (ValueError, TypeError) as exc:
            raise ChainValidationError("Invalid retained chain certificate") from exc
    digests = [
        hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
        for cert in certificates
    ]
    if digests != chain_manifest.get("certificates_sha256_leaf_to_root"):
        raise ChainValidationError("Retained certificate fingerprint mismatch")
    if digests[0] != chain_manifest.get("leaf_sha256") or digests[-1] != chain_manifest.get("root_sha256"):
        raise ChainValidationError("Retained TSA root or signer mismatch")
    return certificates


def _verify_one(crl_der, subject, issuer, at, position):
    if not isinstance(crl_der, bytes) or not 0 < len(crl_der) <= MAX_CRL_BYTES:
        raise ChainValidationError("Unsigned or oversized chain CRL")
    try:
        crl = x509.load_der_x509_crl(crl_der)
        usage = issuer.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE).value
        constraints = issuer.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS).value
        if not constraints.ca or not usage.crl_sign:
            raise ChainValidationError("Chain issuer does not have CRL signing authority")
        if crl.issuer != issuer.subject or subject.issuer != issuer.subject:
            raise ChainValidationError("CRL issuer mismatch")
        # Indirect and delta CRLs require additional issuer/reason processing
        # and must not be treated as complete direct-issued CRL evidence.
        try:
            issuing = crl.extensions.get_extension_for_oid(
                ExtensionOID.ISSUING_DISTRIBUTION_POINT
            ).value
            if issuing.indirect_crl or issuing.only_contains_attribute_certs:
                raise ChainValidationError("Indirect or attribute CRLs unsupported")
            target_ca = subject.extensions.get_extension_for_oid(
                ExtensionOID.BASIC_CONSTRAINTS
            ).value.ca
            if (issuing.only_contains_ca_certs and not target_ca
                    or issuing.only_contains_user_certs and target_ca):
                raise ChainValidationError("CRL distribution point excludes target certificate")
            if issuing.only_some_reasons is not None:
                raise ChainValidationError("Partial-reasons CRLs unsupported")
        except x509.ExtensionNotFound:
            pass
        try:
            crl.extensions.get_extension_for_oid(ExtensionOID.DELTA_CRL_INDICATOR)
        except x509.ExtensionNotFound:
            pass
        else:
            raise ChainValidationError("Delta CRLs require a verified base CRL")
        try:
            aki = crl.extensions.get_extension_for_oid(
                ExtensionOID.AUTHORITY_KEY_IDENTIFIER
            ).value.key_identifier
            if aki is not None:
                ski = issuer.extensions.get_extension_for_oid(
                    ExtensionOID.SUBJECT_KEY_IDENTIFIER
                ).value.digest
                if aki != ski:
                    raise ChainValidationError("CRL issuer key mismatch")
        except x509.ExtensionNotFound:
            pass
        _verify_signature(
            issuer.public_key(), crl.signature,
            crl.tbs_certlist_bytes, crl.signature_hash_algorithm,
        )
        start = _time(getattr(crl, "last_update_utc", None) or crl.last_update)
        end = _time(getattr(crl, "next_update_utc", None) or crl.next_update)
        if not start <= at < end:
            raise ChainValidationError("CRL does not cover historical timestamp generation")
        if crl.get_revoked_certificate_by_serial_number(subject.serial_number) is not None:
            raise ChainValidationError("Certificate revoked in issuer's signed CRL")
    except ChainValidationError:
        raise
    except (ValueError, TypeError, x509.ExtensionNotFound) as exc:
        raise ChainValidationError("Chain CRL signature or authority verification failed") from exc
    return {
        "index": position,
        "subject_sha256": hashlib.sha256(
            subject.public_bytes(serialization.Encoding.DER)
        ).hexdigest(),
        "issuer_sha256": hashlib.sha256(
            issuer.public_bytes(serialization.Encoding.DER)
        ).hexdigest(),
        "crl_sha256": hashlib.sha256(crl_der).hexdigest(),
        "crl_der_b64": base64.b64encode(crl_der).decode("ascii"),
        "this_update": start.isoformat(timespec="microseconds") + "Z",
        "next_update": end.isoformat(timespec="microseconds") + "Z",
        "status": "not_listed_on_issuer_crl",
    }


def validate_chain_crl_inventory(chain_manifest, at, records):
    """Verify saved raw CRLs and report missing non-root certificate positions."""
    certs = _certificates(chain_manifest)
    moment = _time(at)
    if (not isinstance(records, list) or len(records) > len(certs) - 1):
        raise ChainValidationError("Invalid chain revocation inventory")
    found = set()
    checked = []
    for row in records:
        if not isinstance(row, dict) or type(row.get("index")) is not int:
            raise ChainValidationError("Invalid CRL inventory entry")
        index = row["index"]
        if index in found or not 0 <= index < len(certs) - 1:
            raise ChainValidationError("Repeated or invalid certificate position")
        found.add(index)
        try:
            encoded = row["crl_der_b64"]
            if not isinstance(encoded, str) or len(encoded) > 720000:
                raise ValueError("Invalid CRL encoding length")
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, KeyError, TypeError) as exc:
            raise ChainValidationError("Stored chain CRL encoding invalid") from exc
        result = _verify_one(raw, certs[index], certs[index + 1], moment, index)
        if result != row:
            raise ChainValidationError("Stored chain CRL metadata has been altered")
        checked.append(result)
    checked.sort(key=lambda item: item["index"])
    missing = [i for i in range(len(certs) - 1) if i not in found]
    return {
        "schema": "trustseal.chain-crl-inventory.v1",
        "validation_time": moment.isoformat(timespec="microseconds") + "Z",
        "status": "partial" if missing else "non_root_crls_checked",
        "non_root_certificates": len(certs) - 1,
        "covered_positions": [row["index"] for row in checked],
        "missing_positions": missing,
        "observations": checked,
        "full_historical_pkix_assurance": False,
    }


def configured_chain_crls(config, chain_manifest, at):
    """Read one optional DER CRL per non-root chain position, leaf first."""
    raw_config = config.get("VALIDATION_CHAIN_CRL_PATHS_JSON")
    if raw_config is None or raw_config == "":
        return None
    try:
        paths = json.loads(raw_config)
    except (ValueError, TypeError) as exc:
        raise ChainValidationError("Invalid CRL path configuration") from exc
    certs = _certificates(chain_manifest)
    if (not isinstance(paths, list) or len(paths) != len(certs) - 1
            or any(path is not None and (not isinstance(path, str) or not os.path.isabs(path))
                   for path in paths)):
        raise ChainValidationError("CRL paths must align with every non-root certificate")
    rows = []
    at = _time(at)
    for index, name in enumerate(paths):
        if name is None:
            continue
        path = Path(name)
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_CRL_BYTES:
            raise ChainValidationError("Configured CRL path is unavailable or exceeds size limit")
        rows.append(_verify_one(path.read_bytes(), certs[index], certs[index + 1], at, index))
    return validate_chain_crl_inventory(chain_manifest, at, rows)
