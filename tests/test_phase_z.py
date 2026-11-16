"""Phase Z — envelope + document activity timelines."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}


@pytest.fixture
def phase_z_seed(pg_app, tmp_path):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.event_delivery import SecurityEvent
    from app.models.organization import Organization
    from app.models.signing_envelope import SigningEnvelope
    from app.models.user import User

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)

    org = Organization(name="Z Tenant", type="company")
    other_org = Organization(name="Z Other", type="company")
    db.session.add_all([org, other_org])
    db.session.flush()
    owner = User(
        username="z-owner",
        email="z-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-z-password-123")
    other_owner = User(
        username="z-other-owner",
        email="z-other-owner@example.test",
        is_active=True,
        organization_id=other_org.id,
    )
    other_owner.set_password("phase-z-password-123")
    db.session.add_all([owner, other_owner])
    db.session.flush()
    doc = Document(
        title="Z doc",
        status="draft",
        created_by=owner.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()
    body = b"%PDF-1.4\n% z\n%%EOF"
    digest = hashlib.sha256(body).hexdigest()
    (private_root / f"{digest}.pdf").write_bytes(body)
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key=f"{digest}.pdf",
        file_name="z.pdf",
        mime_type="application/pdf",
        file_size=len(body),
        sha256=digest,
        scanner="noop",
        created_by_id=owner.id,
    )
    db.session.add(blob)
    db.session.flush()
    envelope = SigningEnvelope(
        organization_id=org.id,
        document_id=doc.id,
        document_blob_id=blob.id,
        document_sha256=digest,
        created_by_id=owner.id,
        state="prepared",
        prepared_at=datetime.utcnow(),
    )
    db.session.add(envelope)
    db.session.flush()

    base = datetime.utcnow() - timedelta(hours=2)
    rows = []
    # Envelope events — both naming conventions.
    rows.append(
        SecurityEvent(
            organization_id=org.id,
            actor_id=owner.id,
            action="envelope.prepared",
            resource_type="envelope",
            resource_id=envelope.id,
            outcome="ok",
            correlation_id=uuid.uuid4().hex,
            created_at=base + timedelta(minutes=0),
        )
    )
    rows.append(
        SecurityEvent(
            organization_id=org.id,
            actor_id=owner.id,
            action="envelope.auto_withdrawn.expired",
            resource_type="signing_envelope",
            resource_id=envelope.id,
            outcome="ok",
            correlation_id=uuid.uuid4().hex,
            created_at=base + timedelta(minutes=10),
        )
    )
    # Document events.
    for n in range(3):
        rows.append(
            SecurityEvent(
                organization_id=org.id,
                actor_id=owner.id,
                action=f"document.event.{n}",
                resource_type="document",
                resource_id=doc.id,
                outcome="ok",
                correlation_id=uuid.uuid4().hex,
                created_at=base + timedelta(minutes=5 * n),
            )
        )
    # Cross-tenant noise.
    rows.append(
        SecurityEvent(
            organization_id=other_org.id,
            actor_id=None,
            action="envelope.prepared",
            resource_type="envelope",
            resource_id=envelope.id,  # same int, different tenant
            outcome="ok",
            correlation_id=uuid.uuid4().hex,
            created_at=base,
        )
    )
    # Unrelated resource.
    rows.append(
        SecurityEvent(
            organization_id=org.id,
            actor_id=owner.id,
            action="noise.event",
            resource_type="envelope",
            resource_id=envelope.id + 999,
            outcome="ok",
            correlation_id=uuid.uuid4().hex,
            created_at=base,
        )
    )
    db.session.add_all(rows)
    db.session.commit()
    return {
        "org": org,
        "other_org": other_org,
        "owner": owner,
        "other_owner": other_owner,
        "envelope": envelope,
        "document": doc,
    }


# ============================================================ Z1 envelope


class TestEnvelopeActivity:
    def test_returns_both_resource_types(self, pg_app, phase_z_seed):
        client = pg_app.test_client()
        r = client.get(
            f"/api/envelopes/{phase_z_seed['envelope'].id}/activity",
            headers=_auth(phase_z_seed["owner"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["envelope_id"] == phase_z_seed["envelope"].id
        assert len(body["events"]) == 2
        kinds = {row["resource_type"] for row in body["events"]}
        assert kinds == {"envelope", "signing_envelope"}

    def test_scopes_to_tenant(self, pg_app, phase_z_seed):
        """Cross-tenant row with identical resource_id must be excluded."""
        client = pg_app.test_client()
        r = client.get(
            f"/api/envelopes/{phase_z_seed['envelope'].id}/activity",
            headers=_auth(phase_z_seed["owner"]),
        )
        rows = r.get_json()["events"]
        # 2 rows (both from the caller's tenant); cross-tenant is excluded.
        assert len(rows) == 2

    def test_bounds_filter(self, pg_app, phase_z_seed):
        client = pg_app.test_client()
        # Take the "prepared" row's time; window must exclude the later one.
        r = client.get(
            f"/api/envelopes/{phase_z_seed['envelope'].id}/activity",
            headers=_auth(phase_z_seed["owner"]),
        )
        rows = r.get_json()["events"]
        earlier = rows[0]["created_at"]
        narrow = client.get(
            f"/api/envelopes/{phase_z_seed['envelope'].id}/activity"
            f"?since={earlier}&until={earlier}",
            headers=_auth(phase_z_seed["owner"]),
        )
        assert len(narrow.get_json()["events"]) == 1

    def test_envelope_not_found_for_other_tenant(
        self, pg_app, phase_z_seed
    ):
        client = pg_app.test_client()
        r = client.get(
            f"/api/envelopes/{phase_z_seed['envelope'].id}/activity",
            headers=_auth(phase_z_seed["other_owner"]),
        )
        assert r.status_code == 404

    def test_invalid_iso_rejected(self, pg_app, phase_z_seed):
        client = pg_app.test_client()
        r = client.get(
            f"/api/envelopes/{phase_z_seed['envelope'].id}/activity?since=not-a-date",
            headers=_auth(phase_z_seed["owner"]),
        )
        assert r.status_code == 400


# ============================================================ Z2 document


class TestDocumentActivity:
    def test_returns_document_events(self, pg_app, phase_z_seed):
        client = pg_app.test_client()
        r = client.get(
            f"/api/documents/{phase_z_seed['document'].id}/activity",
            headers=_auth(phase_z_seed["owner"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["document_id"] == phase_z_seed["document"].id
        assert len(body["events"]) == 3
        assert {row["action"] for row in body["events"]} == {
            "document.event.0",
            "document.event.1",
            "document.event.2",
        }

    def test_cross_tenant_document_hidden(self, pg_app, phase_z_seed):
        client = pg_app.test_client()
        r = client.get(
            f"/api/documents/{phase_z_seed['document'].id}/activity",
            headers=_auth(phase_z_seed["other_owner"]),
        )
        assert r.status_code == 404

    def test_limit_out_of_range(self, pg_app, phase_z_seed):
        client = pg_app.test_client()
        r = client.get(
            f"/api/documents/{phase_z_seed['document'].id}/activity?limit=999",
            headers=_auth(phase_z_seed["owner"]),
        )
        assert r.status_code == 400
