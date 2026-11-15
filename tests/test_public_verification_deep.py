"""Deep public verification contract (G13).

Covers the service layer directly and the HTTP endpoint routing:

* Service ``deep_verify``:
    - Returns ``unknown`` when no retention matches the digest.
    - Returns ``mismatch`` when the uploaded bytes don't hash to the
      claimed digest.
    - Returns ``unavailable`` with a specific reason when a retention
      exists but has no dossier yet, or the dossier's timestamp was
      deleted.
    - Returns ``invalid`` when the dossier manifest has been
      tampered or a referenced revocation row is missing.
    - Returns ``valid`` and a populated verdict when
      :func:`validation_dossier.verify_dossier` reproduces the
      manifest cleanly.

* API endpoint ``/api/public-verification/pdf``:
    - With ``PUBLIC_VERIFICATION_DEEP_ENABLED=true`` routes to the
      deep path and returns ``deep_dossier_verification`` assurance.
    - ``asserted_sha256`` mismatch returns ``mismatch`` without
      hitting the DB.
    - When only the shallow flag is set, legacy behaviour is
      preserved.
    - When neither flag is set, returns 503.

Heavy TSA/PKIX plumbing is replaced with a monkey-patched
``verify_dossier`` so these tests focus on routing and verdict
mapping; the full cryptographic path has its own integration
coverage.
"""
from __future__ import annotations

import hashlib
import io
from datetime import datetime

import pytest


@pytest.fixture
def tenant(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.user import User

    org = Organization(name="DeepVerify Tenant")
    db.session.add(org)
    db.session.flush()
    user = User(
        username="deep-ops",
        email="deep-ops@example.test",
        is_active=True,
        organization_id=org.id,
    )
    user.set_password("not-used-strong-password")
    db.session.add(user)
    db.session.commit()
    return {"org": org, "user": user}


def _sample_pdf(body: bytes = b"") -> bytes:
    return b"%PDF-1.4\n% deep-verify probe\n" + body + b"\n%%EOF\n"


def _seed_retention(org_id: int, user_id: int, artifact_bytes: bytes):
    """Seed a retention row keyed to the sha256 of ``artifact_bytes``."""
    from datetime import timedelta

    from app.extensions import db
    from app.models.evidence_preservation import EvidenceRetention

    digest = hashlib.sha256(artifact_bytes).hexdigest()
    retention = EvidenceRetention(
        organization_id=org_id,
        artifact_type="finalized_pdf",
        artifact_id=1,
        artifact_sha256=digest,
        retain_until=datetime.utcnow() + timedelta(days=365),
        created_by_id=user_id,
    )
    db.session.add(retention)
    db.session.commit()
    return retention, digest


def _seed_dossier_chain(retention, user_id: int):
    """Add a timestamp + dossier + OCSP row referenced by the dossier.

    The verifier is mocked, so the stored manifest is minimal; only the
    structural binding (retention_id / timestamp_id) and the
    ``revocation_observations`` list matter for the service wiring.
    """
    from app.extensions import db
    from app.models.evidence_timestamp import EvidenceTimestamp
    from app.models.ocsp_evidence import OcspEvidence
    from app.models.validation_dossier import ValidationDossier

    timestamp = EvidenceTimestamp(
        retention_id=retention.id,
        organization_id=retention.organization_id,
        operator_id=user_id,
        tsa_certificate_sha256="c" * 64,
        token_sha256="d" * 64,
        token_der_b64="abc",
        artifact_sha256=retention.artifact_sha256,
        gen_time=datetime.utcnow(),
    )
    db.session.add(timestamp)
    db.session.flush()
    from datetime import timedelta

    ocsp = OcspEvidence(
        organization_id=retention.organization_id,
        timestamp_id=timestamp.id,
        subject_certificate_sha256=timestamp.tsa_certificate_sha256,
        issuer_certificate_sha256="e" * 64,
        response_sha256="f" * 64,
        response_der_b64="xyz",
        subject_der_b64="pem-subject",
        issuer_der_b64="pem-issuer",
        produced_at=timestamp.gen_time,
        this_update=timestamp.gen_time,
        next_update=timestamp.gen_time + timedelta(seconds=1),
        checked_at=timestamp.gen_time,
        operator_id=user_id,
        status="good",
    )
    db.session.add(ocsp)
    db.session.flush()
    manifest = {
        "schema": "trustseal.validation-dossier.v1",
        "revocation_observations": [
            {
                "type": "ocsp",
                "id": ocsp.id,
                "sha256": ocsp.response_sha256,
                "subject_sha256": ocsp.subject_certificate_sha256,
                "checked_at": "ignored-in-mocked-tests",
            }
        ],
    }
    dossier = ValidationDossier(
        retention_id=retention.id,
        organization_id=retention.organization_id,
        operator_id=user_id,
        timestamp_id=timestamp.id,
        manifest=manifest,
        manifest_sha256="d" * 64,
    )
    db.session.add(dossier)
    db.session.commit()
    return timestamp, dossier, ocsp


# --- service-layer --------------------------------------------------


class TestServiceLayer:
    def test_unknown_digest(self, pg_app, tenant):
        from app.services.public_verification import deep_verify

        data = _sample_pdf(b"unseen")
        digest = hashlib.sha256(data).hexdigest()
        result = deep_verify(digest, data, pg_app.config)
        assert result.verdict == "unknown"
        assert result.retention_id is None

    def test_mismatch_when_bytes_differ(self, pg_app, tenant):
        """The uploaded bytes hash must match the supplied digest."""
        from app.services.public_verification import deep_verify

        other = _sample_pdf(b"other")
        tampered = _sample_pdf(b"tampered")
        _ret, digest = _seed_retention(tenant["org"].id, tenant["user"].id, other)
        result = deep_verify(digest, tampered, pg_app.config)
        assert result.verdict == "mismatch"
        assert result.reason == "document_sha256_differs"

    def test_no_dossier_yet(self, pg_app, tenant):
        from app.services.public_verification import deep_verify

        payload = _sample_pdf(b"only-retention")
        retention, digest = _seed_retention(
            tenant["org"].id, tenant["user"].id, payload
        )
        result = deep_verify(digest, payload, pg_app.config)
        assert result.verdict == "unavailable"
        assert result.reason == "no_dossier"
        assert result.retention_id == retention.id

    def test_invalid_input(self, pg_app):
        from app.services.public_verification import deep_verify

        with pytest.raises(ValueError):
            deep_verify("notahex", b"%PDF-", pg_app.config)
        with pytest.raises(ValueError):
            deep_verify("a" * 64, b"", pg_app.config)

    def test_tampered_dossier_surfaces_invalid(self, pg_app, tenant, monkeypatch):
        from app.services import public_verification, validation_dossier

        payload = _sample_pdf(b"full-chain")
        retention, digest = _seed_retention(
            tenant["org"].id, tenant["user"].id, payload
        )
        _seed_dossier_chain(retention, tenant["user"].id)

        def _fake(*args, **kwargs):
            raise ValueError("Dossier evidence differs from retained signed sources")

        monkeypatch.setattr(validation_dossier, "verify_dossier", _fake)
        monkeypatch.setattr(public_verification.dossier_service, "verify_dossier", _fake)

        result = public_verification.deep_verify(digest, payload, pg_app.config)
        assert result.verdict == "invalid"
        assert "Dossier evidence differs" in (result.reason or "")

    def test_valid_path_returns_populated_verdict(
        self, pg_app, tenant, monkeypatch
    ):
        from app.services import public_verification, validation_dossier

        payload = _sample_pdf(b"valid-path")
        retention, digest = _seed_retention(
            tenant["org"].id, tenant["user"].id, payload
        )
        timestamp, _dossier, ocsp = _seed_dossier_chain(retention, tenant["user"].id)

        def _fake(dossier, retention, ts, ocsp_rows, crl_rows, config):
            return {
                "schema": "trustseal.validation-dossier.v1",
                "assurance": "partial_tsa_status_evidence_not_full_chain_or_pades_lt",
                "complete": False,
                "timestamp": {
                    "gen_time": "2026-01-01T00:00:00.000000Z",
                    "tsa_certificate_sha256": ts.tsa_certificate_sha256,
                    "token_sha256": ts.token_sha256,
                },
                "revocation_observations": [
                    {
                        "type": "ocsp",
                        "id": ocsp.id,
                        "sha256": ocsp.response_sha256,
                        "subject_sha256": ocsp.subject_certificate_sha256,
                        "checked_at": "2026-01-01T00:00:00.000000Z",
                    }
                ],
                "missing_requirements": ["tsa_crl_observation"],
                "certificate_chain": {
                    "leaf_sha256": ts.tsa_certificate_sha256,
                    "intermediate_sha256s": [],
                },
                "platform_signer_chain": {
                    "signer_certificate_sha256": "a" * 64,
                    "crl_inventory": {},
                },
            }

        monkeypatch.setattr(validation_dossier, "verify_dossier", _fake)
        monkeypatch.setattr(public_verification.dossier_service, "verify_dossier", _fake)

        result = public_verification.deep_verify(digest, payload, pg_app.config)
        assert result.verdict == "valid"
        assert result.retention_id == retention.id
        assert result.timestamp["tsa_certificate_sha256"] == timestamp.tsa_certificate_sha256
        assert result.revocation_observations
        assert "tsa_crl_observation" in result.missing_requirements
        assert result.certificate_chain["leaf_sha256"] == timestamp.tsa_certificate_sha256
        assert result.platform_signer_chain["signer_certificate_sha256"] == "a" * 64


# --- HTTP endpoint --------------------------------------------------


class TestEndpoint:
    def test_neither_flag_returns_503(self, pg_app):
        pg_app.config["PUBLIC_PDF_VERIFICATION_ENABLED"] = False
        pg_app.config["PUBLIC_VERIFICATION_DEEP_ENABLED"] = False
        r = pg_app.test_client().post(
            "/api/public-verification/pdf",
            data={"evidence_sha256": "a" * 64,
                  "pdf": (io.BytesIO(_sample_pdf()), "x.pdf")},
            content_type="multipart/form-data",
        )
        assert r.status_code == 503
        body = r.get_json()
        assert body["status"] == "unavailable"

    def test_deep_path_returns_deep_assurance(self, pg_app, tenant, monkeypatch):
        """With deep enabled the endpoint uses the dossier verifier."""
        from app.services import public_verification, validation_dossier

        pg_app.config["PUBLIC_VERIFICATION_DEEP_ENABLED"] = True
        pg_app.config["PUBLIC_PDF_VERIFICATION_ENABLED"] = False
        payload = _sample_pdf(b"endpoint-valid")
        retention, _digest = _seed_retention(
            tenant["org"].id, tenant["user"].id, payload
        )
        ts, _dossier, ocsp = _seed_dossier_chain(retention, tenant["user"].id)

        def _fake(dossier, retention, ts_arg, ocsp_rows, crl_rows, config):
            return {
                "timestamp": {
                    "gen_time": "2026-01-01T00:00:00.000000Z",
                    "tsa_certificate_sha256": ts_arg.tsa_certificate_sha256,
                    "token_sha256": ts_arg.token_sha256,
                },
                "revocation_observations": [
                    {
                        "type": "ocsp",
                        "id": ocsp.id,
                        "sha256": ocsp.response_sha256,
                        "subject_sha256": ocsp.subject_certificate_sha256,
                        "checked_at": "2026-01-01T00:00:00.000000Z",
                    }
                ],
                "missing_requirements": [],
            }

        monkeypatch.setattr(validation_dossier, "verify_dossier", _fake)
        monkeypatch.setattr(public_verification.dossier_service, "verify_dossier", _fake)

        r = pg_app.test_client().post(
            "/api/public-verification/pdf",
            data={"pdf": (io.BytesIO(payload), "x.pdf")},
            content_type="multipart/form-data",
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["status"] == "valid"
        assert body["assurance"] == "deep_dossier_verification"
        assert body["retention_id"] == retention.id
        assert body["timestamp"]["tsa_certificate_sha256"] == ts.tsa_certificate_sha256
        assert body["revocation_observations"]
        assert body["missing_requirements"] == []

    def test_deep_path_unknown_digest_hides_retention_state(self, pg_app):
        pg_app.config["PUBLIC_VERIFICATION_DEEP_ENABLED"] = True
        pg_app.config["PUBLIC_PDF_VERIFICATION_ENABLED"] = False
        payload = _sample_pdf(b"never-seen")
        r = pg_app.test_client().post(
            "/api/public-verification/pdf",
            data={"pdf": (io.BytesIO(payload), "x.pdf")},
            content_type="multipart/form-data",
        )
        body = r.get_json()
        assert r.status_code == 200
        assert body["status"] == "unknown"
        assert "retention_id" not in body

    def test_deep_path_asserted_mismatch_short_circuits(self, pg_app, tenant):
        pg_app.config["PUBLIC_VERIFICATION_DEEP_ENABLED"] = True
        pg_app.config["PUBLIC_PDF_VERIFICATION_ENABLED"] = False
        payload = _sample_pdf(b"short-circuit")
        r = pg_app.test_client().post(
            "/api/public-verification/pdf",
            data={
                "pdf": (io.BytesIO(payload), "x.pdf"),
                "artifact_sha256": "b" * 64,
            },
            content_type="multipart/form-data",
        )
        body = r.get_json()
        assert r.status_code == 200
        assert body["status"] == "mismatch"
        assert body["reason"] == "document_sha256_differs"
        assert body["asserted_sha256"] == "b" * 64

    def test_shallow_fallback_still_works(self, pg_app, tenant):
        pg_app.config["PUBLIC_VERIFICATION_DEEP_ENABLED"] = False
        pg_app.config["PUBLIC_PDF_VERIFICATION_ENABLED"] = True
        pg_app.config["PUBLIC_PDF_VERIFICATION_CERT_SHA256"] = "a" * 64
        r = pg_app.test_client().post(
            "/api/public-verification/pdf",
            data={
                "evidence_sha256": "b" * 64,
                "pdf": (io.BytesIO(_sample_pdf()), "x.pdf"),
            },
            content_type="multipart/form-data",
        )
        # The shallow path returns ``invalid`` for a PDF without a real
        # embedded signature. The important check is that the endpoint
        # advertises the legacy assurance rather than deep.
        assert r.status_code == 200
        assert r.get_json()["assurance"] == "platform_certificate_seal_only"
