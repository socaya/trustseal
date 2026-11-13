"""Independent PDF signer chain purpose and historical CRL tests."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from app.services.explicit_certificate_chain import ChainValidationError
from app.services.platform_signer_chain import build_platform_chain
from tests.test_explicit_certificate_chain import build, key, pem


def _configured(tmp_path, *, wrong_purpose=False):
    at = datetime(2026, 11, 13, tzinfo=timezone.utc)
    root_key = key()
    root = build("Platform Root", root_key, None, None, at,
                 ca=True, path_length=1)
    intermediate_key = key()
    middle = build("Platform Intermediate", intermediate_key, root, root_key,
                   at, ca=True, path_length=0)
    signer_key = key()
    leaf = build("TrustSeal Platform Seal", signer_key, middle, intermediate_key,
                 at, ca=False, tsa=wrong_purpose)
    paths = []
    for name, value in (("seal.pem", leaf), ("issuer.pem", middle),
                        ("root.pem", root)):
        path = tmp_path / name
        path.write_bytes(pem(value))
        paths.append(str(path))
    config = {
        "VALIDATION_PDF_SEAL_CERT_PEM": paths[0],
        "VALIDATION_PDF_INTERMEDIATES_JSON": json.dumps([paths[1]]),
        "PDF_TRUST_ROOT_PEM": paths[2],
    }
    return at, config, leaf, middle, root, intermediate_key, root_key


def _crl(issuer, issuer_key, at, serial=None):
    builder = (
        x509.CertificateRevocationListBuilder()
        .issuer_name(issuer.subject)
        .last_update(at - timedelta(days=1))
        .next_update(at + timedelta(days=1))
    )
    if serial is not None:
        builder = builder.add_revoked_certificate(
            x509.RevokedCertificateBuilder()
            .serial_number(serial)
            .revocation_date(at - timedelta(hours=3))
            .build()
        )
    return builder.sign(issuer_key, hashes.SHA256()).public_bytes(
        serialization.Encoding.DER
    )


def test_platform_certificate_path_is_distinct_from_tsa(tmp_path):
    at, config, leaf, middle, root, _, _ = _configured(tmp_path)
    fingerprint = hashlib.sha256(
        leaf.public_bytes(serialization.Encoding.DER)
    ).hexdigest()
    report = build_platform_chain(
        config, certificate_sha256=fingerprint, at=at
    )
    assert report["schema"] == "trustseal.platform-pdf-chain-evidence.v1"
    assert report["certificate_chain"]["leaf_sha256"] == fingerprint
    assert report["certificate_chain"]["complete_pkix_validation"] is False
    assert "crl_inventory" not in report
    assert build_platform_chain(
        config, certificate_sha256=fingerprint, at=at, retained=report
    ) == report
    with pytest.raises(ChainValidationError):
        build_platform_chain(config, certificate_sha256="f" * 64, at=at)
    with pytest.raises(ChainValidationError):
        build_platform_chain(config, certificate_sha256=fingerprint,
                             at=at + timedelta(days=90))


def test_platform_certificate_does_not_accept_tsa_only_eku(tmp_path):
    at, config, leaf, _, _, _, _ = _configured(tmp_path, wrong_purpose=True)
    fingerprint = hashlib.sha256(
        leaf.public_bytes(serialization.Encoding.DER)
    ).hexdigest()
    with pytest.raises(ChainValidationError, match="TSA-only"):
        build_platform_chain(config, certificate_sha256=fingerprint, at=at)


def test_platform_signer_crls_are_bound_to_both_issuers(tmp_path):
    at, config, leaf, middle, root, middle_key, root_key = _configured(tmp_path)
    leaf_digest = hashlib.sha256(
        leaf.public_bytes(serialization.Encoding.DER)
    ).hexdigest()
    crl_paths = []
    for i, der in enumerate((
        _crl(middle, middle_key, at),
        _crl(root, root_key, at),
    )):
        file = tmp_path / ("issuer-%s.crl" % i)
        file.write_bytes(der)
        crl_paths.append(str(file))
    config["VALIDATION_PDF_CHAIN_CRL_PATHS_JSON"] = json.dumps(crl_paths)
    report = build_platform_chain(
        config, certificate_sha256=leaf_digest, at=at
    )
    assert report["crl_inventory"]["status"] == "non_root_crls_checked"
    assert report["crl_inventory"]["missing_positions"] == []
    assert build_platform_chain(
        config, certificate_sha256=leaf_digest, at=at, retained=report
    ) == report

    # Changing the signed CRL after issuance cannot alter the historical
    # snapshot; changing its recorded bytes or digest must be detected.
    crl_paths and (tmp_path / "issuer-0.crl").write_bytes(
        _crl(middle, middle_key, at, serial=leaf.serial_number)
    )
    with pytest.raises(ChainValidationError):
        build_platform_chain(config, certificate_sha256=leaf_digest, at=at)
    assert build_platform_chain(
        config, certificate_sha256=leaf_digest, at=at, retained=report
    ) == report
    report["crl_inventory"]["observations"][0]["crl_sha256"] = "0" * 64
    with pytest.raises(ChainValidationError):
        build_platform_chain(config, certificate_sha256=leaf_digest,
                             at=at, retained=report)


def test_platform_signer_rejects_wrong_path_configuration(tmp_path):
    at, config, leaf, _, _, _, _ = _configured(tmp_path)
    digest = hashlib.sha256(
        leaf.public_bytes(serialization.Encoding.DER)
    ).hexdigest()
    config["VALIDATION_PDF_INTERMEDIATES_JSON"] = '["relative.pem"]'
    with pytest.raises(ChainValidationError):
        build_platform_chain(config, certificate_sha256=digest, at=at)
