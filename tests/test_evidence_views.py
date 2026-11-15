"""Evidence dossier viewer (/evidence) contract.

Covers:

* Anonymous callers are redirected to login.
* A tenant member sees only their tenant's retentions.
* A retention id from another tenant returns 404 (ADR 0003
  anti-enumeration).
* The dossier page renders every section (checkpoints, timestamps,
  OCSP, CRL, dossiers, DSS, holds).
* The checkpoint chain-break integrity probe surfaces a break.
* The chain-ok path is labelled explicitly.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from flask_login import login_user


@pytest.fixture
def seeded(pg_app):
    from app.extensions import db
    from app.models.evidence_preservation import (
        EvidenceCheckpoint,
        EvidenceLegalHold,
        EvidenceRetention,
    )
    from app.models.evidence_timestamp import EvidenceTimestamp
    from app.models.organization import Organization
    from app.models.user import User

    tenant_a = Organization(name="Evidence A")
    tenant_b = Organization(name="Evidence B")
    db.session.add_all([tenant_a, tenant_b])
    db.session.flush()

    user_a = User(
        username="viewer-a",
        email="viewer-a@example.test",
        is_active=True,
        organization_id=tenant_a.id,
    )
    user_a.set_password("not-used")
    user_b = User(
        username="viewer-b",
        email="viewer-b@example.test",
        is_active=True,
        organization_id=tenant_b.id,
    )
    user_b.set_password("not-used")
    db.session.add_all([user_a, user_b])
    db.session.flush()

    retention_a = EvidenceRetention(
        organization_id=tenant_a.id,
        artifact_type="finalized_pdf",
        artifact_id=1,
        artifact_sha256="a" * 64,
        retain_until=datetime.utcnow() + timedelta(days=365),
        created_by_id=user_a.id,
    )
    retention_b = EvidenceRetention(
        organization_id=tenant_b.id,
        artifact_type="finalized_pdf",
        artifact_id=2,
        artifact_sha256="b" * 64,
        retain_until=datetime.utcnow() + timedelta(days=365),
        created_by_id=user_b.id,
    )
    db.session.add_all([retention_a, retention_b])
    db.session.flush()

    hold = EvidenceLegalHold(
        retention_id=retention_a.id,
        organization_id=tenant_a.id,
        reason="Active litigation",
        requested_by_id=user_a.id,
    )
    checkpoint_one = EvidenceCheckpoint(
        retention_id=retention_a.id,
        organization_id=tenant_a.id,
        operator_id=user_a.id,
        payload={"digest": "first-digest"},
        signature="sig-one",
        algorithm="Ed25519",
        key_id="ed25519-sha256:probe",
    )
    db.session.add_all([hold, checkpoint_one])
    db.session.flush()
    checkpoint_two = EvidenceCheckpoint(
        retention_id=retention_a.id,
        organization_id=tenant_a.id,
        operator_id=user_a.id,
        payload={"digest": "second-digest", "previous_digest": "first-digest"},
        signature="sig-two",
        algorithm="Ed25519",
        key_id="ed25519-sha256:probe",
    )
    db.session.add(checkpoint_two)
    db.session.flush()
    timestamp = EvidenceTimestamp(
        retention_id=retention_a.id,
        organization_id=tenant_a.id,
        operator_id=user_a.id,
        tsa_certificate_sha256="c" * 64,
        token_sha256="d" * 64,
        token_der_b64="abc",
        artifact_sha256="a" * 64,
        gen_time=datetime.utcnow(),
    )
    db.session.add(timestamp)
    db.session.commit()
    return {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "user_a": user_a,
        "user_b": user_b,
        "retention_a": retention_a,
        "retention_b": retention_b,
        "checkpoint_two": checkpoint_two,
    }


def _login(app, user):
    """Establish a Flask-Login session for ``user``."""
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True
        yield client


class TestAccessControl:
    def test_anonymous_redirected(self, pg_app):
        r = pg_app.test_client().get("/evidence/retentions")
        # Flask-Login redirects anonymous callers to the login view.
        assert r.status_code in {302, 401}

    def test_tenant_a_sees_only_own_retentions(self, pg_app, seeded):
        for client in _login(pg_app, seeded["user_a"]):
            r = client.get("/evidence/retentions")
            assert r.status_code == 200
            body = r.data.decode("utf-8")
            assert "Evidence retentions" in body
            # Tenant A's digest is present; tenant B's is not.
            assert "a" * 64 in body
            assert "b" * 64 not in body

    def test_cross_tenant_retention_returns_404(self, pg_app, seeded):
        for client in _login(pg_app, seeded["user_a"]):
            r = client.get(
                f"/evidence/retentions/{seeded['retention_b'].id}"
            )
            assert r.status_code == 404


class TestDossierRendering:
    def test_full_page_renders_all_sections(self, pg_app, seeded):
        for client in _login(pg_app, seeded["user_a"]):
            r = client.get(
                f"/evidence/retentions/{seeded['retention_a'].id}"
            )
            assert r.status_code == 200
            body = r.data.decode("utf-8")
            assert "Canonical digest" in body
            assert "Legal holds" in body
            assert "Checkpoints" in body
            assert "Timestamps" in body
            assert "OCSP responses" in body
            assert "CRL evidence" in body
            assert "Validation dossiers" in body
            assert "PDF DSS derivatives" in body

    def test_integrity_chain_ok_surfaced(self, pg_app, seeded):
        for client in _login(pg_app, seeded["user_a"]):
            r = client.get(
                f"/evidence/retentions/{seeded['retention_a'].id}"
            )
            body = r.data.decode("utf-8")
            assert "chain consistent" in body

    def test_integrity_chain_break_surfaced(self, pg_app, seeded):
        from app.extensions import db

        seeded["checkpoint_two"].payload = {"digest": "x", "previous_digest": "wrong"}
        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(seeded["checkpoint_two"], "payload")
        db.session.commit()
        for client in _login(pg_app, seeded["user_a"]):
            r = client.get(
                f"/evidence/retentions/{seeded['retention_a'].id}"
            )
            body = r.data.decode("utf-8")
            assert "chain break" in body


class TestIntegrityUnit:
    def test_single_checkpoint_counts_as_ok(self, pg_app):
        from app.blueprints.trust.views.evidence_views import _check_checkpoint_chain
        from app.models.evidence_preservation import EvidenceCheckpoint

        result = _check_checkpoint_chain(
            [
                EvidenceCheckpoint(
                    id=1, payload={"digest": "first"},
                )
            ]
        )
        assert result["status"] == "chain_ok"
        assert result["break_at"] is None

    def test_empty_list(self):
        from app.blueprints.trust.views.evidence_views import _check_checkpoint_chain

        result = _check_checkpoint_chain([])
        assert result["status"] == "no_checkpoints"
