"""Real signed PDF incremental DSS test with bounded ASN.1 validation evidence.

The test CRL is synthetic and does not establish real-life revocation trust.
The purpose is checking pyHanko's incremental update and CMS preservation.
"""
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.services.pdf_dss import (
    DssEvidenceError, collect_dss_material, append_dss_derivative,
    verify_dss_derivative,
)
from app.services.platform_pdf_seal import inspect_signed_pdf
from tests.integration.test_platform_pdf_roundtrip import _sample_pdf


def _sample_material(signing_config):
    # Use the actual platform leaf and trust root for a parsable DER chain.
    from cryptography.hazmat.primitives.serialization import pkcs12
    with open(signing_config["PDF_PLATFORM_PKCS12"], "rb") as stream:
        raw = stream.read()
    key, leaf, others = pkcs12.load_key_and_certificates(
        raw, signing_config["PDF_PLATFORM_PKCS12_PASSWORD"].encode(),
    )
    certificates = [leaf, others[0]]
    chain_der = [
        cert.public_bytes(serialization.Encoding.DER) for cert in certificates
    ]
    signer = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    test_crl = (
        x509.CertificateRevocationListBuilder()
        .issuer_name(others[0].subject)
        .last_update(now - timedelta(hours=1))
        .next_update(now + timedelta(hours=1))
        .sign(signer, hashes.SHA256())
        .public_bytes(serialization.Encoding.DER)
    )
    row = SimpleNamespace(
        id=17,
        crl_der_b64=base64.b64encode(test_crl).decode(),
    )
    digest = hashlib.sha256(test_crl).hexdigest()
    dossier = SimpleNamespace(manifest={
        "assurance": "partial_tsa_status_evidence_not_full_chain_or_pades_lt",
        "complete": False,
        "certificate_chain": {
            "certificates_der_b64_leaf_to_root": [
                base64.b64encode(part).decode() for part in chain_der
            ],
            "certificates_sha256_leaf_to_root": [
                hashlib.sha256(part).hexdigest() for part in chain_der
            ],
        },
        "revocation_observations": [{
            "type": "crl", "id": 17, "sha256": digest,
        }],
    })
    return dossier, row


def test_incremental_dss_derivative_preserves_platform_signature(signing_config):
    from app.services.platform_pdf_seal import seal_pdf
    original, fingerprint, _ = seal_pdf(
        _sample_pdf(), signing_config, "a" * 64,
    )
    dossier, crl = _sample_material(signing_config)
    result = append_dss_derivative(
        original, dossier, [], [crl], signing_config,
        evidence_sha256="a" * 64, certificate_sha256=fingerprint,
    )
    assert result.startswith(original)
    assert result != original
    assert inspect_signed_pdf(
        original, signing_config, expected_evidence_sha256="a" * 64,
        expected_certificate_sha256=fingerprint,
    )["overall_valid"]
    assert verify_dss_derivative(
        original, result, hashlib.sha256(result).hexdigest(),
        signing_config, evidence_sha256="a" * 64,
        certificate_sha256=fingerprint,
    )["overall_valid"]
    with pytest.raises(DssEvidenceError):
        verify_dss_derivative(
            original, result + b"changed", hashlib.sha256(result).hexdigest(),
            signing_config, evidence_sha256="a" * 64,
            certificate_sha256=fingerprint,
        )


def test_dss_material_rejects_missing_and_tampered_crl(signing_config):
    dossier, crl = _sample_material(signing_config)
    with pytest.raises(DssEvidenceError):
        collect_dss_material(dossier, [], [])
    crl.crl_der_b64 = base64.b64encode(b"not-the-original-crl").decode()
    with pytest.raises(DssEvidenceError):
        collect_dss_material(dossier, [], [crl])


def test_dss_material_not_claimed_lt_without_validation_chain():
    dossier = SimpleNamespace(manifest={
        "complete": False,
        "assurance": "partial_tsa_status_evidence_not_full_chain_or_pades_lt",
        "revocation_observations": [],
    })
    with pytest.raises(DssEvidenceError):
        collect_dss_material(dossier, [], [])
