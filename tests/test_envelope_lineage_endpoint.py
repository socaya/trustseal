"""Envelope lineage endpoint (I6).

Covers:

* An envelope with no lineage pointers returns a single-entry chain.
* An envelope that was reissued returns both links: the original (now
  ``superseded``) and the current draft.
* The ``is_current`` flag marks the envelope the caller asked about.
* Cross-tenant access returns 404.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

import pytest
from flask_jwt_extended import create_access_token


@pytest.fixture
def seeded(pg_app, tmp_path):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.signing_envelope import (
        EnvelopeParticipant,
        SigningEnvelope,
    )
    from app.models.user import User

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)

    org_a = Organization(name="Lineage A", type="company")
    org_b = Organization(name="Lineage B", type="company")
    db.session.add_all([org_a, org_b])
    db.session.flush()

    def mk_user(name, email, org):
        u = User(
            username=name,
            email=email,
            is_active=True,
            organization_id=org.id,
        )
        u.set_password("lineagepassword12345")
        db.session.add(u)
        db.session.flush()
        return u

    creator = mk_user("lineage-creator", "lineage-creator@example.test", org_a)
    signer = mk_user("lineage-signer", "lineage-signer@example.test", org_a)
    foreign = mk_user("lineage-foreign", "lineage-foreign@example.test", org_b)

    doc = Document(
        title="Lineage doc",
        status="draft",
        created_by=creator.id,
        organization_id=org_a.id,
    )
    db.session.add(doc)
    db.session.flush()
    body = b"%PDF-1.4\n% lineage\n%%EOF"
    digest = hashlib.sha256(body).hexdigest()
    (private_root / f"{digest}.pdf").write_bytes(body)
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key=f"{digest}.pdf",
        file_name="lineage.pdf",
        mime_type="application/pdf",
        file_size=len(body),
        sha256=digest,
        scanner="noop",
        created_by_id=creator.id,
    )
    db.session.add(blob)
    db.session.flush()
    envelope = SigningEnvelope(
        organization_id=org_a.id,
        document_id=doc.id,
        document_blob_id=blob.id,
        document_sha256=digest,
        created_by_id=creator.id,
        state="prepared",
        prepared_at=datetime.utcnow(),
        preview_confirmed_at=datetime.utcnow(),
    )
    db.session.add(envelope)
    db.session.flush()
    db.session.add(
        EnvelopeParticipant(
            envelope_id=envelope.id,
            user_id=signer.id,
            signing_order=1,
            role="signer",
        )
    )
    db.session.commit()
    return {
        "org_a": org_a,
        "org_b": org_b,
        "creator": creator,
        "signer": signer,
        "foreign": foreign,
        "envelope": envelope,
    }


class TestLineage:
    def test_single_entry_when_no_lineage(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["creator"].id))
        r = client.get(
            f"/api/envelopes/{seeded['envelope'].id}/lineage",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        body = r.get_json()
        assert body["current_envelope_id"] == seeded["envelope"].id
        assert len(body["chain"]) == 1
        assert body["chain"][0]["id"] == seeded["envelope"].id
        assert body["chain"][0]["is_current"] is True

    def test_reissued_chain(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["creator"].id))
        r = client.post(
            f"/api/envelopes/{seeded['envelope'].id}/reissue",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"lineage-reissue-{seeded['envelope'].id}",
            },
        )
        assert r.status_code == 201
        clone_id = r.get_json()["id"]
        # Ask lineage for the clone — should return [original, clone].
        r = client.get(
            f"/api/envelopes/{clone_id}/lineage",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.get_json()
        ids = [c["id"] for c in body["chain"]]
        assert ids == [seeded["envelope"].id, clone_id]
        current = [c for c in body["chain"] if c["is_current"]]
        assert len(current) == 1
        assert current[0]["id"] == clone_id
        # Original is marked superseded.
        original_entry = [
            c for c in body["chain"] if c["id"] == seeded["envelope"].id
        ][0]
        assert original_entry["state"] == "superseded"

    def test_cross_tenant_is_404(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["foreign"].id))
        r = client.get(
            f"/api/envelopes/{seeded['envelope'].id}/lineage",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404
