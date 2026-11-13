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


def test_signed_chain_crls_bind_both_leaf_and_intermediate(tmp_path):
    import base64
    import hashlib
    import json
    from app.services.chain_crl_inventory import (
        configured_chain_crls, validate_chain_crl_inventory,
    )
    at = datetime(2026, 11, 13, tzinfo=timezone.utc)
    root_key = key()
    root = build("CRL Root", root_key, None, None, at, ca=True, path_length=1)
    issuer_key = key()
    issuer = build("CRL Intermediate", issuer_key, root, root_key, at,
                   ca=True, path_length=0)
    leaf_key = key()
    leaf = build("CRL TSA", leaf_key, issuer, issuer_key, at, ca=False, tsa=True)
    chain_manifest = validate_explicit_chain(
        pem(leaf), [pem(issuer)], pem(root), at,
    )

    def signed_crl(issuer_cert, signing_key, *, revoked_serial=None,
                   bad_key=False, expired=False):
        builder = (
            x509.CertificateRevocationListBuilder()
            .issuer_name(issuer_cert.subject)
            .last_update(at - timedelta(days=4 if expired else 1))
            .next_update(at - timedelta(days=1) if expired else at + timedelta(days=1))
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(
                    signing_key.public_key()
                ),
                critical=False,
            )
        )
        if revoked_serial is not None:
            builder = builder.add_revoked_certificate(
                x509.RevokedCertificateBuilder()
                .serial_number(revoked_serial)
                .revocation_date(at - timedelta(hours=4))
                .build()
            )
        return builder.sign(
            key() if bad_key else signing_key, hashes.SHA256()
        ).public_bytes(serialization.Encoding.DER)

    first = signed_crl(issuer, issuer_key)
    second = signed_crl(root, root_key)
    paths = []
    for number, raw in enumerate([first, second]):
        path = tmp_path / ("chain-%s.crl" % number)
        path.write_bytes(raw)
        paths.append(str(path))
    config = {"VALIDATION_CHAIN_CRL_PATHS_JSON": json.dumps(paths)}
    inventory = configured_chain_crls(config, chain_manifest, at)
    assert inventory["status"] == "non_root_crls_checked"
    assert inventory["covered_positions"] == [0, 1]
    assert inventory["missing_positions"] == []
    assert inventory["full_historical_pkix_assurance"] is False
    assert validate_chain_crl_inventory(
        chain_manifest, at, inventory["observations"]
    ) == inventory

    # A partial inventory is never a positive assertion for the missing CA.
    config["VALIDATION_CHAIN_CRL_PATHS_JSON"] = json.dumps([paths[0], None])
    partial = configured_chain_crls(config, chain_manifest, at)
    assert partial["status"] == "partial"
    assert partial["missing_positions"] == [1]

    # The first signed CRL is valid, but missing the second issuer's status.
    edited = [dict(row) for row in inventory["observations"]]
    edited[0]["crl_sha256"] = "f" * 64
    with pytest.raises(ChainValidationError):
        validate_chain_crl_inventory(chain_manifest, at, edited)
    edited = [dict(row) for row in inventory["observations"]]
    edited.append(dict(edited[0]))
    with pytest.raises(ChainValidationError):
        validate_chain_crl_inventory(chain_manifest, at, edited)

    for altered in (
        signed_crl(issuer, issuer_key, revoked_serial=leaf.serial_number),
        signed_crl(issuer, issuer_key, expired=True),
        signed_crl(issuer, issuer_key, bad_key=True),
    ):
        (tmp_path / "chain-0.crl").write_bytes(altered)
        with pytest.raises(ChainValidationError):
            configured_chain_crls(config, chain_manifest, at)


def test_chain_crls_reject_untrusted_configuration_and_misordered_evidence(tmp_path):
    import json
    from app.services.chain_crl_inventory import configured_chain_crls
    at, (leaf, middle, root) = chain()
    dossier_chain = validate_explicit_chain(leaf, [middle], root, at)
    for unsafe in ('not-json', '["relative.crl", null]', '[]',
                   '[null]', '[false, null]'):
        with pytest.raises(ChainValidationError):
            configured_chain_crls(
                {"VALIDATION_CHAIN_CRL_PATHS_JSON": unsafe},
                dossier_chain, at,
            )
