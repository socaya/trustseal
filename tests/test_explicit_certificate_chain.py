"""Cryptographic tests of an explicit TSA trust chain and historical validity."""
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID

from app.services.explicit_certificate_chain import (
    ChainValidationError, validate_explicit_chain, chain_from_config,
)


def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def ca_usage():
    return x509.KeyUsage(
        digital_signature=True, content_commitment=False,
        key_encipherment=False, data_encipherment=False,
        key_agreement=False, key_cert_sign=True, crl_sign=True,
        encipher_only=False, decipher_only=False,
    )


def signer_usage():
    return x509.KeyUsage(
        digital_signature=True, content_commitment=True,
        key_encipherment=False, data_encipherment=False,
        key_agreement=False, key_cert_sign=False, crl_sign=False,
        encipher_only=False, decipher_only=False,
    )


def build(subject, subject_key, issuer, issuer_key, now, *,
          ca, path_length=None, expired=False, tsa=False):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject)])
    parent_name = issuer.subject if issuer else name
    builder = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(parent_name)
        .public_key(subject_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=30))
        .not_valid_after(now - timedelta(days=1) if expired else now + timedelta(days=30))
        .add_extension(
            x509.BasicConstraints(ca=ca, path_length=path_length),
            critical=True,
        )
        .add_extension(ca_usage() if ca else signer_usage(), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(subject_key.public_key()),
            critical=False,
        )
    )
    if issuer is not None:
        builder = builder.add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(
                issuer_key.public_key(),
            ),
            critical=False,
        )
    if tsa:
        builder = builder.add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]),
            critical=True,
        )
    return builder.sign(issuer_key or subject_key, hashes.SHA256())


def pem(cert):
    return cert.public_bytes(serialization.Encoding.PEM)


def chain(*, root_path_length=1, expired_intermediate=False, leaf_tsa=True,
          alternate_signer=False):
    now = datetime(2026, 11, 13, tzinfo=timezone.utc)
    root_key = key()
    root = build("Offline Root", root_key, None, None, now,
                 ca=True, path_length=root_path_length)
    intermediate_key = key()
    intermediate = build(
        "Offline Intermediate", intermediate_key, root, root_key, now,
        ca=True, path_length=0, expired=expired_intermediate,
    )
    tsa_key = key()
    tsa = build(
        "Timestamp Signer", tsa_key, intermediate,
        key() if alternate_signer else intermediate_key, now,
        ca=False, tsa=leaf_tsa,
    )
    return now, [pem(tsa), pem(intermediate), pem(root)]


def test_valid_intermediate_path_is_bound_at_historical_time():
    now, (leaf, issuer, root) = chain()
    result = validate_explicit_chain(leaf, [issuer], root, now)
    assert result["complete_pkix_validation"] is False
    assert result["revocation_verified_for_entire_chain"] is False
    assert len(result["certificates_sha256_leaf_to_root"]) == 3
    assert len(result["certificates_der_b64_leaf_to_root"]) == 3
    assert result["leaf_sha256"] != result["root_sha256"]


@pytest.mark.parametrize("changes", [
    {"root_path_length": 0},
    {"expired_intermediate": True},
    {"leaf_tsa": False},
    {"alternate_signer": True},
])
def test_invalid_chain_issuer_constraints_and_signature_are_rejected(changes):
    now, (leaf, issuer, root) = chain(**changes)
    with pytest.raises(ChainValidationError):
        validate_explicit_chain(leaf, [issuer], root, now)


def test_untrusted_root_order_and_wrong_validation_time_rejected():
    now, (leaf, issuer, root) = chain()
    _, (_, _, unrelated_root) = chain()
    with pytest.raises(ChainValidationError):
        validate_explicit_chain(leaf, [issuer], unrelated_root, now)
    with pytest.raises(ChainValidationError):
        validate_explicit_chain(leaf, [root, issuer], root, now)
    with pytest.raises(ChainValidationError):
        validate_explicit_chain(leaf, [issuer], root, now + timedelta(days=60))


def test_config_requires_exact_ordered_pinned_paths(tmp_path):
    now, (leaf, issuer, root) = chain()
    files = []
    for name, data in (("leaf.pem", leaf), ("issuer.pem", issuer), ("root.pem", root)):
        path = tmp_path / name
        path.write_bytes(data)
        files.append(path)
    import json
    config = {
        "RFC3161_TSA_CERT_PEM": str(files[0]),
        "RFC3161_TRUST_ROOT_PEM": str(files[2]),
        "VALIDATION_TSA_INTERMEDIATES_JSON": json.dumps([str(files[1])]),
    }
    assert chain_from_config(config, now)["validation_time"].startswith("2026-11-13")
    config["VALIDATION_TSA_INTERMEDIATES_JSON"] = "not JSON"
    with pytest.raises(ChainValidationError):
        chain_from_config(config, now)
