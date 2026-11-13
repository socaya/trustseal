"""Deterministic partial-dossier reconstruction and tamper rejection."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services.validation_dossier import (
    ASSURANCE, SCHEMA, build_dossier, digest_manifest, verify_dossier,
)


def fixtures():
    retention = SimpleNamespace(
        id=12, organization_id=7, artifact_type="finalized_pdf",
        artifact_id=31, artifact_sha256="a" * 64,
    )
    token = SimpleNamespace(
        id=8, retention_id=12, organization_id=7,
        artifact_sha256="a" * 64, token_sha256="b" * 64,
        tsa_certificate_sha256="c" * 64, gen_time=datetime(2026, 11, 13),
        token_der_b64="opaque",
    )
    return retention, token


def patch_trust(monkeypatch):
    from app.services import validation_dossier as service
    monkeypatch.setattr(service, "decode_token", lambda _: b"timestamp")
    monkeypatch.setattr(service, "verify_timestamp", lambda raw, digest, config: {
        "token_sha256": "b" * 64,
        "tsa_certificate_sha256": "c" * 64,
        "gen_time": datetime(2026, 11, 13),
    })
    monkeypatch.setattr(service, "_read_pem", lambda *args: b"test-root")
    monkeypatch.setattr(service, "artifact_for", lambda *args: SimpleNamespace(
        output_sha256="a" * 64
    ))
    monkeypatch.setattr(service, "verify_artifact", lambda *args: "a" * 64)
    monkeypatch.setattr(service, "verify_ocsp_snapshot", lambda *args: {
        "status": "good", "subject_certificate_sha256": "c" * 64,
    })
    monkeypatch.setattr(service, "verify_snapshot", lambda *args: {
        "status": "good", "subject_certificate_sha256": "c" * 64,
    })


def test_dossier_never_overclaims_complete_pkix_validation(monkeypatch):
    patch_trust(monkeypatch)
    retention, token = fixtures()
    report = build_dossier(retention, token, [], [], {})
    assert report["schema"] == SCHEMA
    assert report["assurance"] == ASSURANCE
    assert report["complete"] is False
    assert "full_certificate_path_validation" in report["missing_requirements"]
    assert "tsa_ocsp_observation" in report["missing_requirements"]
    assert "tsa_crl_observation" in report["missing_requirements"]
    assert len(digest_manifest(report)) == 64


def test_observations_bounded_to_same_tsa_and_reproducible(monkeypatch):
    patch_trust(monkeypatch)
    retention, token = fixtures()
    ocsp = SimpleNamespace(
        id=25, timestamp_id=token.id, organization_id=7,
        status="good", response_sha256="d" * 64,
        checked_at=datetime(2026, 11, 13),
    )
    crl = SimpleNamespace(
        id=26, timestamp_id=token.id, organization_id=7,
        status="good", crl_sha256="e" * 64,
        checked_at=datetime(2026, 11, 13),
    )
    manifest = build_dossier(retention, token, [ocsp], [crl], {})
    assert len(manifest["revocation_observations"]) == 2
    assert "tsa_crl_observation" not in manifest["missing_requirements"]
    assert manifest["complete"] is False
    record = SimpleNamespace(
        retention_id=12, organization_id=7, timestamp_id=8,
        manifest=manifest, manifest_sha256=digest_manifest(manifest),
    )
    assert verify_dossier(record, retention, token, [ocsp], [crl], {}) == manifest
    record.manifest_sha256 = "f" * 64
    with pytest.raises(ValueError):
        verify_dossier(record, retention, token, [ocsp], [crl], {})
    ocsp.organization_id = 99
    with pytest.raises(ValueError):
        build_dossier(retention, token, [ocsp], [crl], {})


def test_wrong_retention_digest_and_duplicate_observation_are_denied(monkeypatch):
    patch_trust(monkeypatch)
    retention, token = fixtures()
    token.artifact_sha256 = "f" * 64
    with pytest.raises(ValueError):
        build_dossier(retention, token, [], [], {})
    token.artifact_sha256 = "a" * 64
    observation = SimpleNamespace(
        id=9, timestamp_id=token.id, organization_id=7,
        status="good", response_sha256="d" * 64,
        checked_at=datetime(2026, 11, 13),
    )
    with pytest.raises(ValueError):
        build_dossier(retention, token, [observation, observation], [], {})


def test_revoked_observation_is_never_counted_as_good(monkeypatch):
    patch_trust(monkeypatch)
    retention, token = fixtures()
    row = SimpleNamespace(
        id=5, timestamp_id=token.id, organization_id=7,
        status="revoked", crl_sha256="f" * 64,
        checked_at=datetime(2026, 11, 13),
    )
    with pytest.raises(ValueError):
        build_dossier(retention, token, [], [row], {})


def test_legacy_dossier_without_chain_metadata_remains_verifiable(monkeypatch):
    patch_trust(monkeypatch)
    retention, token = fixtures()
    legacy = build_dossier(
        retention, token, [], [], {},
        chain_mode="none", report_missing_chain=False,
    )
    assert "certificate_chain" not in legacy
    assert "bounded_explicit_tsa_certificate_path" not in legacy["missing_requirements"]
    record = SimpleNamespace(
        retention_id=retention.id, organization_id=retention.organization_id,
        timestamp_id=token.id, manifest=legacy,
        manifest_sha256=digest_manifest(legacy),
    )
    assert verify_dossier(record, retention, token, [], [], {}) == legacy


def test_explicit_tsa_chain_is_recorded_but_never_upgrades_assurance(monkeypatch):
    patch_trust(monkeypatch)
    from app.services import validation_dossier as service
    retention, token = fixtures()
    chain = {
        "schema": "trustseal.explicit-tsa-chain.v1",
        "leaf_sha256": token.tsa_certificate_sha256,
        "root_sha256": "d" * 64,
        "complete_pkix_validation": False,
    }
    monkeypatch.setattr(service, "chain_from_config", lambda config, when: chain)
    manifest = build_dossier(retention, token, [], [], {})
    assert manifest["certificate_chain"] == chain
    assert manifest["complete"] is False
    assert "full_certificate_path_validation" in manifest["missing_requirements"]
    dossier = SimpleNamespace(
        retention_id=12, organization_id=7, timestamp_id=8,
        manifest=manifest, manifest_sha256=digest_manifest(manifest),
    )
    assert verify_dossier(dossier, retention, token, [], [], {}) == manifest
    chain["leaf_sha256"] = "e" * 64
    with pytest.raises(ValueError):
        verify_dossier(dossier, retention, token, [], [], {})


def test_historical_chain_crl_inventory_is_retained_and_reverified(monkeypatch):
    patch_trust(monkeypatch)
    from app.services import validation_dossier as service
    retention, token = fixtures()
    chain = {
        "schema": "trustseal.explicit-tsa-chain.v1",
        "leaf_sha256": token.tsa_certificate_sha256,
        "root_sha256": "d" * 64,
        "complete_pkix_validation": False,
    }
    inventory = {
        "schema": "trustseal.chain-crl-inventory.v1",
        "status": "partial",
        "missing_positions": [1],
        "observations": [{"index": 0, "crl_sha256": "e" * 64}],
        "full_historical_pkix_assurance": False,
    }
    monkeypatch.setattr(service, "chain_from_config", lambda cfg, now: chain)
    monkeypatch.setattr(
        service, "configured_chain_crls",
        lambda cfg, manifest, now: inventory,
    )
    monkeypatch.setattr(
        service, "validate_chain_crl_inventory",
        lambda manifest, now, entries: inventory if entries == inventory["observations"] else {},
    )
    manifest = build_dossier(retention, token, [], [], {})
    assert manifest["chain_revocation"] == inventory
    assert manifest["complete"] is False
    record = SimpleNamespace(
        retention_id=retention.id, organization_id=retention.organization_id,
        timestamp_id=token.id, manifest=manifest,
        manifest_sha256=digest_manifest(manifest),
    )
    assert verify_dossier(record, retention, token, [], [], {}) == manifest
    record.manifest["chain_revocation"]["observations"][0]["crl_sha256"] = "f" * 64
    with pytest.raises(ValueError):
        verify_dossier(record, retention, token, [], [], {})
