"""Envelope correction / reissue lineage (F3).

Covers:

* ``POST /api/envelopes/<id>/reissue`` on a prepared envelope
  creates a new draft that mirrors participants + fields and points
  at the original via ``supersedes_envelope_id``.
* The original's ``state`` flips to ``superseded`` and its
  ``superseded_by_envelope_id`` points forward.
* Field values are NOT carried over — the clone starts fresh.
* Re-reissue of an already-superseded envelope returns 409.
* Reissue of a draft envelope returns 409 (only terminal states can
  be reissued).
* Withdrawn + cancelled envelopes keep their state but still record
  the forward pointer.
"""
from __future__ import annotations

import hashlib
import io
from datetime import datetime
from pathlib import Path

import pytest
from flask_jwt_extended import create_access_token


@pytest.fixture
def seeded(pg_app, tmp_path):
    """Prepared envelope with two signers + one text field."""
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.envelope_field import EnvelopeField
    from app.models.organization import Organization
    from app.models.signing_envelope import (
        EnvelopeParticipant,
        SigningEnvelope,
    )
    from app.models.user import User

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)

    org = Organization(name="Lineage Tenant", type="company")
    db.session.add(org)
    db.session.flush()

    def mk(name, email):
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

    creator = mk("lineage-creator", "lineage-creator@example.test")
    signer_a = mk("lineage-signer-a", "lineage-signer-a@example.test")
    signer_b = mk("lineage-signer-b", "lineage-signer-b@example.test")

    doc = Document(
        title="Lineage doc",
        status="draft",
        created_by=creator.id,
        organization_id=org.id,
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
        organization_id=org.id,
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
    p_a = EnvelopeParticipant(
        envelope_id=envelope.id,
        user_id=signer_a.id,
        signing_order=1,
        role="signer",
    )
    p_b = EnvelopeParticipant(
        envelope_id=envelope.id,
        user_id=signer_b.id,
        signing_order=2,
        role="signer",
    )
    db.session.add_all([p_a, p_b])
    db.session.flush()
    field = EnvelopeField(
        envelope_id=envelope.id,
        participant_id=p_a.id,
        field_type="text",
        page_number=1,
        x_pt=10,
        y_pt=20,
        width_pt=120,
        height_pt=40,
        required=True,
        value="old value",
        submitted_at=datetime.utcnow(),
        created_by_id=creator.id,
    )
    db.session.add(field)
    db.session.commit()
    return {
        "org": org,
        "creator": creator,
        "envelope": envelope,
        "participants": [p_a, p_b],
        "field": field,
    }


class TestReissue:
    def test_reissue_prepared_envelope(self, pg_app, seeded):
        from app.extensions import db
        from app.models.envelope_field import EnvelopeField
        from app.models.signing_envelope import (
            EnvelopeParticipant,
            SigningEnvelope,
        )

        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["creator"].id))
        r = client.post(
            f"/api/envelopes/{seeded['envelope'].id}/reissue",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"reissue-{seeded['envelope'].id}",
            },
        )
        assert r.status_code == 201, r.get_data(as_text=True)
        clone = r.get_json()
        assert clone["state"] == "draft"
        assert clone["supersedes_envelope_id"] == seeded["envelope"].id
        # Original state + forward pointer updated.
        db.session.expire_all()
        original = db.session.get(
            SigningEnvelope, seeded["envelope"].id
        )
        assert original.state == "superseded"
        assert original.superseded_by_envelope_id == clone["id"]
        # Participants were copied.
        new_participants = (
            EnvelopeParticipant.query.filter_by(envelope_id=clone["id"])
            .order_by(EnvelopeParticipant.signing_order.asc())
            .all()
        )
        assert [p.user_id for p in new_participants] == [
            seeded["participants"][0].user_id,
            seeded["participants"][1].user_id,
        ]
        # Fields were copied without values.
        new_fields = EnvelopeField.query.filter_by(
            envelope_id=clone["id"]
        ).all()
        assert len(new_fields) == 1
        assert new_fields[0].value is None
        assert new_fields[0].submitted_at is None

    def test_double_reissue_refused(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["creator"].id))
        r = client.post(
            f"/api/envelopes/{seeded['envelope'].id}/reissue",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"reissue-first-{seeded['envelope'].id}",
            },
        )
        assert r.status_code == 201
        r2 = client.post(
            f"/api/envelopes/{seeded['envelope'].id}/reissue",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"reissue-second-{seeded['envelope'].id}",
            },
        )
        assert r2.status_code == 409

    def test_reissue_draft_refused(self, pg_app, seeded):
        from app.extensions import db

        seeded["envelope"].state = "draft"
        seeded["envelope"].prepared_at = None
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["creator"].id))
        r = client.post(
            f"/api/envelopes/{seeded['envelope'].id}/reissue",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"reissue-draft-{seeded['envelope'].id}",
            },
        )
        assert r.status_code == 409

    def test_reissue_withdrawn_keeps_terminal_state(self, pg_app, seeded):
        from app.extensions import db
        from app.models.signing_envelope import SigningEnvelope

        seeded["envelope"].state = "withdrawn"
        seeded["envelope"].withdrawn_at = datetime.utcnow()
        seeded["envelope"].withdrawn_by_id = seeded["creator"].id
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["creator"].id))
        r = client.post(
            f"/api/envelopes/{seeded['envelope'].id}/reissue",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"reissue-withdrawn-{seeded['envelope'].id}",
            },
        )
        assert r.status_code == 201
        db.session.expire_all()
        original = db.session.get(
            SigningEnvelope, seeded["envelope"].id
        )
        assert original.state == "withdrawn"  # terminal state preserved
        assert original.superseded_by_envelope_id == r.get_json()["id"]
