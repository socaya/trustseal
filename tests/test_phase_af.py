"""Phase AF — participant reorder + tenant-wide envelope labels."""
from __future__ import annotations

import hashlib
from datetime import datetime

import pytest
from flask_jwt_extended import create_access_token


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}


@pytest.fixture
def phase_af_seed(pg_app, tmp_path):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.signing_envelope import (
        EnvelopeLabel,
        EnvelopeParticipant,
        SigningEnvelope,
    )
    from app.models.user import User

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)
    org = Organization(name="AF Tenant", type="company")
    other_org = Organization(name="AF Other", type="company")
    db.session.add_all([org, other_org])
    db.session.flush()
    owner = User(
        username="af-owner",
        email="af-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-af-password-123")
    intruder = User(
        username="af-intruder",
        email="af-intruder@example.test",
        is_active=True,
        organization_id=other_org.id,
    )
    intruder.set_password("phase-af-password-123")
    db.session.add_all([owner, intruder])
    db.session.flush()
    signers = []
    for n in range(3):
        u = User(
            username=f"af-signer-{n}",
            email=f"af-signer-{n}@example.test",
            is_active=True,
            organization_id=org.id,
        )
        u.set_password("phase-af-password-123")
        db.session.add(u)
        db.session.flush()
        signers.append(u)
    doc = Document(
        title="AF doc",
        status="draft",
        created_by=owner.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()
    body = b"%PDF-1.4\n% af\n%%EOF"
    digest = hashlib.sha256(body).hexdigest()
    (private_root / f"{digest}.pdf").write_bytes(body)
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key=f"{digest}.pdf",
        file_name="af.pdf",
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
        state="draft",
    )
    db.session.add(envelope)
    db.session.flush()
    participants = []
    for idx, s in enumerate(signers):
        p = EnvelopeParticipant(
            envelope_id=envelope.id,
            user_id=s.id,
            signing_order=idx + 1,
            role="signer",
        )
        db.session.add(p)
        db.session.flush()
        participants.append(p)
    # Pre-seed some labels for tenant-wide listing. "finance" is
    # attached to two different envelopes to prove the per-label
    # count aggregates across the tenant.
    doc2 = Document(
        title="AF doc 2",
        status="draft",
        created_by=owner.id,
        organization_id=org.id,
    )
    db.session.add(doc2)
    db.session.flush()
    envelope2 = SigningEnvelope(
        organization_id=org.id,
        document_id=doc2.id,
        document_blob_id=blob.id,
        document_sha256=digest,
        created_by_id=owner.id,
        state="draft",
    )
    db.session.add(envelope2)
    db.session.flush()
    for env_id, label in (
        (envelope.id, "finance"),
        (envelope.id, "hr"),
        (envelope2.id, "finance"),
    ):
        db.session.add(
            EnvelopeLabel(
                envelope_id=env_id,
                organization_id=org.id,
                label=label,
                created_by_id=owner.id,
            )
        )
    db.session.commit()
    return {
        "org": org,
        "owner": owner,
        "intruder": intruder,
        "envelope": envelope,
        "participants": participants,
    }


# ============================================================ AF1 reorder


class TestParticipantReorder:
    def test_reorder_to_unused_slot(self, pg_app, phase_af_seed):
        from app.extensions import db
        from app.models.signing_envelope import EnvelopeParticipant

        client = pg_app.test_client()
        p = phase_af_seed["participants"][0]
        # Participant 0 is order=1. Move it to a free order.
        # First move p3 out of the way: set p3 to 99, then p0 to 3.
        p3 = phase_af_seed["participants"][2]
        r = client.patch(
            f"/api/envelopes/{phase_af_seed['envelope'].id}"
            f"/participants/{p3.id}",
            json={"signing_order": 99},
            headers=_auth(phase_af_seed["owner"]),
        )
        assert r.status_code == 200
        r = client.patch(
            f"/api/envelopes/{phase_af_seed['envelope'].id}"
            f"/participants/{p.id}",
            json={"signing_order": 3},
            headers=_auth(phase_af_seed["owner"]),
        )
        assert r.status_code == 200
        assert r.get_json()["signing_order"] == 3
        db.session.expire_all()
        refreshed = db.session.get(EnvelopeParticipant, p.id)
        assert refreshed.signing_order == 3

    def test_reorder_duplicate_rejected(self, pg_app, phase_af_seed):
        client = pg_app.test_client()
        p = phase_af_seed["participants"][0]  # order=1
        r = client.patch(
            f"/api/envelopes/{phase_af_seed['envelope'].id}"
            f"/participants/{p.id}",
            json={"signing_order": 2},  # taken by p2
            headers=_auth(phase_af_seed["owner"]),
        )
        assert r.status_code == 409

    def test_same_order_noop(self, pg_app, phase_af_seed):
        client = pg_app.test_client()
        p = phase_af_seed["participants"][0]
        r = client.patch(
            f"/api/envelopes/{phase_af_seed['envelope'].id}"
            f"/participants/{p.id}",
            json={"signing_order": 1},
            headers=_auth(phase_af_seed["owner"]),
        )
        assert r.status_code == 200
        assert r.get_json()["changed"] is False

    def test_non_draft_rejected(self, pg_app, phase_af_seed):
        from app.extensions import db

        phase_af_seed["envelope"].state = "prepared"
        db.session.commit()
        client = pg_app.test_client()
        p = phase_af_seed["participants"][0]
        r = client.patch(
            f"/api/envelopes/{phase_af_seed['envelope'].id}"
            f"/participants/{p.id}",
            json={"signing_order": 99},
            headers=_auth(phase_af_seed["owner"]),
        )
        assert r.status_code == 409

    def test_bad_order_rejected(self, pg_app, phase_af_seed):
        client = pg_app.test_client()
        p = phase_af_seed["participants"][0]
        r = client.patch(
            f"/api/envelopes/{phase_af_seed['envelope'].id}"
            f"/participants/{p.id}",
            json={"signing_order": 0},
            headers=_auth(phase_af_seed["owner"]),
        )
        assert r.status_code == 400

    def test_unknown_participant_404(self, pg_app, phase_af_seed):
        client = pg_app.test_client()
        r = client.patch(
            f"/api/envelopes/{phase_af_seed['envelope'].id}"
            f"/participants/9999999",
            json={"signing_order": 99},
            headers=_auth(phase_af_seed["owner"]),
        )
        assert r.status_code == 404


# ============================================================ AF2 tenant labels


class TestTenantLabelList:
    def test_returns_unique_labels_with_counts(self, pg_app, phase_af_seed):
        client = pg_app.test_client()
        r = client.get(
            "/api/envelopes/labels", headers=_auth(phase_af_seed["owner"])
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["organization_id"] == phase_af_seed["org"].id
        label_map = {row["label"]: row["count"] for row in body["labels"]}
        # Seed added two 'finance' rows + one 'hr' row.
        assert label_map == {"finance": 2, "hr": 1}

    def test_scopes_to_tenant(self, pg_app, phase_af_seed):
        client = pg_app.test_client()
        r = client.get(
            "/api/envelopes/labels",
            headers=_auth(phase_af_seed["intruder"]),
        )
        assert r.status_code == 200
        # Intruder sees nothing from the other tenant.
        assert r.get_json()["labels"] == []
