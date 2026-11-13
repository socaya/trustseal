"""Bounded platform PDF signer-chain evidence, distinct from TSA validation.

The RFC 3161 timestamp token refers to the finalized PDF hash, providing
a bounded validation instant. This is NOT a trusted PDF signature time:
document creation could have occurred earlier, and policy/list validation
and full PKIX semantics remain unresolved.
"""
import hashlib
import json

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from app.services.certificate_revocation import _read_pem, RevocationEvidenceError
from app.services.explicit_certificate_chain import (
    ChainValidationError, MAX_INTERMEDIATES, validate_explicit_chain,
)
from app.services.chain_crl_inventory import (
    configured_chain_crls, validate_chain_crl_inventory,
)

SCHEMA = "trustseal.platform-pdf-chain-evidence.v1"


def _paths(config):
    value = config.get("VALIDATION_PDF_INTERMEDIATES_JSON") or "[]"
    try:
        paths = json.loads(value)
    except (ValueError, TypeError) as exc:
        raise ChainValidationError("PDF intermediate configuration invalid") from exc
    if (not isinstance(paths, list) or len(paths) > MAX_INTERMEDIATES
            or any(not isinstance(path, str) for path in paths)):
        raise ChainValidationError("Invalid PDF signer intermediate paths")
    return paths


def build_platform_chain(config, *, certificate_sha256, at,
                         retained=None, include_new_crls=True):
    root = config.get("PDF_TRUST_ROOT_PEM")
    leaf = config.get("VALIDATION_PDF_SEAL_CERT_PEM")
    if not leaf:
        if retained is not None:
            raise ChainValidationError("Historical PDF signer certificate unavailable")
        return None
    if not root:
        raise ChainValidationError("Approved platform PDF root unavailable")
    try:
        chain = validate_explicit_chain(
            _read_pem(leaf, "PDF platform signer"),
            [_read_pem(path, "PDF intermediate") for path in _paths(config)],
            _read_pem(root, "PDF platform trusted root"),
            at, purpose="pdf_seal",
        )
    except RevocationEvidenceError as exc:
        raise ChainValidationError("Approved PDF signer certificate files invalid") from exc
    if chain["leaf_sha256"] != certificate_sha256:
        raise ChainValidationError("PDF signing certificate does not match sealed PDF")
    if retained is not None:
        if not isinstance(retained, dict) or retained.get("schema") != SCHEMA:
            raise ChainValidationError("Historical PDF chain manifest invalid")
        inventory = retained.get("crl_inventory")
        if inventory is not None:
            validated = validate_chain_crl_inventory(
                chain, at, inventory.get("observations", []),
            )
            if validated != inventory:
                raise ChainValidationError("Retained PDF signer CRLs differ")
        report = {
            "schema": SCHEMA,
            "certificate_chain": chain,
        }
        if inventory is not None:
            report["crl_inventory"] = validated
        if report != retained:
            raise ChainValidationError("Historical PDF signer chain altered")
        return report
    report = {"schema": SCHEMA, "certificate_chain": chain}
    if include_new_crls:
        inventory_config = config.get("VALIDATION_PDF_CHAIN_CRL_PATHS_JSON")
        if inventory_config:
            inventory = configured_chain_crls(
                {"VALIDATION_CHAIN_CRL_PATHS_JSON": inventory_config},
                chain, at,
            )
            if inventory is not None:
                report["crl_inventory"] = inventory
    return report
