"""Phase V — operator attachment review + usage CSV export."""
from __future__ import annotations

import csv
import hashlib
import io
from datetime import datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token


# ============================================================ V1 attachments


@pytest.fixture
def v1_seed(pg_app, tmp_path):
    """Seed an envelope + decision + two bound attachments."""
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.signer_attachment import SignerAttachment
    from app.models.signer_decision import SignerChallenge, SignerDecision
    from app.models.signing_envelope import (
        EnvelopeParticipant,
        SigningEnvelope,
    )
    from app.models.user import User
    from app.services.documents.private_object_store import active_store

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)
    pg_app.config["PRIVATE_STORAGE_BACKEND"] = "filesystem"

    org = Organization(name="V Tenant", type="company")
    other_org = Organization(name="V Other Tenant", type="company")
    db.session.add_all([org, other_org])
    db.session.flush()
    owner = User(
        username="v-owner",
        email="v-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-v-password-123")
    signer = User(
        username="v-signer",
        email="v-signer@example.test",
        is_active=True,
        organization_id=org.id,
    )
    signer.set_password("phase-v-password-123")
    db.session.add_all([owner, signer])
    db.session.flush()
    doc = Document(
        title="V doc",
        status="draft",
        created_by=owner.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()
    body = b"%PDF-1.4\n% v\n%%EOF"
    digest = hashlib.sha256(body).hexdigest()
    (private_root / f"{digest}.pdf").write_bytes(body)
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key=f"{digest}.pdf",
        file_name="v.pdf",
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
    participant = EnvelopeParticipant(
        envelope_id=envelope.id,
        user_id=signer.id,
        signing_order=1,
        role="signer",
    )
    db.session.add(participant)
    db.session.flush()
    challenge = SignerChallenge(
        envelope_id=envelope.id,
        participant_id=participant.id,
        user_id=signer.id,
        document_sha256=digest,
        nonce_sha256="n" * 64,
        issued_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=5),
        consumed_at=datetime.utcnow(),
    )
    db.session.add(challenge)
    db.session.flush()
    decision = SignerDecision(
        envelope_id=envelope.id,
        participant_id=participant.id,
        user_id=signer.id,
        challenge_id=challenge.id,
        decision="acknowledged",
        document_sha256=digest,
        consent_version="review-intent-v1",
        consent_sha256="d" * 64,
        recorded_at=datetime.utcnow(),
    )
    db.session.add(decision)
    db.session.flush()

    store = active_store(pg_app.config)
    attachments = []
    for n, payload in enumerate([
        b"\x89PNG\r\n\x1a\nattachment-one",
        b"%PDF-1.4\n% attachment-two\n%%EOF",
    ]):
        result = store.put(payload, config=pg_app.config)
        row = SignerAttachment(
            envelope_id=envelope.id,
            participant_id=participant.id,
            user_id=signer.id,
            decision_id=decision.id,
            organization_id=org.id,
            object_key=result.key,
            file_name=f"evidence-{n}.bin",
            mime_type="image/png" if n == 0 else "application/pdf",
            file_size=result.size,
            sha256=result.sha256,
            scanner="noop",
        )
        db.session.add(row)
        db.session.flush()
        attachments.append((row, payload))
    db.session.commit()
    return {
        "org": org,
        "other_org": other_org,
        "owner": owner,
        "signer": signer,
        "envelope": envelope,
        "attachments": attachments,
    }


class TestAttachmentReview:
    def test_list_returns_bound_attachments(self, pg_app, v1_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(v1_seed["owner"].id))
        r = client.get(
            f"/api/envelopes/{v1_seed['envelope'].id}/attachments",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["envelope_id"] == v1_seed["envelope"].id
        assert len(body["attachments"]) == 2
        shas = {row["sha256"] for row in body["attachments"]}
        assert shas == {
            v1_seed["attachments"][0][0].sha256,
            v1_seed["attachments"][1][0].sha256,
        }

    def test_download_round_trip(self, pg_app, v1_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(v1_seed["owner"].id))
        row, payload = v1_seed["attachments"][0]
        r = client.get(
            f"/api/envelopes/{v1_seed['envelope'].id}"
            f"/attachments/{row.id}/download",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.data == payload
        assert r.headers["X-TrustSeal-Attachment-SHA256"] == row.sha256

    def test_staged_attachment_not_downloadable(
        self, pg_app, v1_seed
    ):
        """An attachment without decision_id must stay invisible to the operator."""
        from app.extensions import db
        from app.models.signer_attachment import SignerAttachment
        from app.services.documents.private_object_store import active_store

        store = active_store(pg_app.config)
        payload = b"\x89PNG\r\n\x1a\nstaged"
        result = store.put(payload, config=pg_app.config)
        staged = SignerAttachment(
            envelope_id=v1_seed["envelope"].id,
            participant_id=v1_seed["envelope"].id,  # placeholder — not bound
            user_id=v1_seed["signer"].id,
            organization_id=v1_seed["org"].id,
            object_key=result.key,
            file_name="staged.png",
            mime_type="image/png",
            file_size=result.size,
            sha256=result.sha256,
            scanner="noop",
        )
        db.session.add(staged)
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(v1_seed["owner"].id))
        r = client.get(
            f"/api/envelopes/{v1_seed['envelope'].id}"
            f"/attachments/{staged.id}/download",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404

    def test_cross_tenant_envelope_rejected(self, pg_app, v1_seed):
        """A different tenant's token cannot download an attachment."""
        from app.extensions import db
        from app.models.user import User

        intruder = User(
            username="intruder",
            email="intruder@example.test",
            is_active=True,
            organization_id=v1_seed["other_org"].id,
        )
        intruder.set_password("phase-v-password-123")
        db.session.add(intruder)
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(intruder.id))
        row, _ = v1_seed["attachments"][0]
        r = client.get(
            f"/api/envelopes/{v1_seed['envelope'].id}"
            f"/attachments/{row.id}/download",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404


# ============================================================ V2 usage CSV


@pytest.fixture
def v2_seed(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.system import Role, UserRole
    from app.models.usage_ledger import UsageLedgerEntry
    from app.models.user import User

    org = Organization(name="V Usage Tenant", type="company")
    other_org = Organization(name="V Usage Other", type="company")
    db.session.add_all([org, other_org])
    db.session.flush()
    role = Role.query.filter_by(name="admin").one_or_none() or Role(
        name="admin", description="test"
    )
    db.session.add(role)
    db.session.flush()
    admin = User(
        username="v-usage-admin",
        email="v-usage-admin@example.test",
        is_active=True,
        organization_id=org.id,
    )
    admin.set_password("phase-v-password-123")
    db.session.add(admin)
    db.session.flush()
    db.session.add(UserRole(user_id=admin.id, role_id=role.id))
    regular = User(
        username="v-usage-regular",
        email="v-usage-regular@example.test",
        is_active=True,
        organization_id=org.id,
    )
    regular.set_password("phase-v-password-123")
    db.session.add(regular)
    db.session.flush()
    base = datetime.utcnow() - timedelta(days=1)
    rows = []
    for idx, meter in enumerate(
        ["envelopes.prepared", "envelopes.prepared", "pdfs.sealed", "verifies.ok"]
    ):
        rows.append(
            UsageLedgerEntry(
                organization_id=org.id,
                meter=meter,
                source_event_id=f"evt-{idx}",
                hits=1,
                recorded_at=base + timedelta(hours=idx),
                actor_id=admin.id,
            )
        )
    # Cross-tenant noise.
    rows.append(
        UsageLedgerEntry(
            organization_id=other_org.id,
            meter="envelopes.prepared",
            source_event_id="evt-cross",
            hits=1,
            recorded_at=base,
        )
    )
    db.session.add_all(rows)
    db.session.commit()
    return {"org": org, "admin": admin, "regular": regular, "rows": rows}


class TestUsageCSV:
    def test_admin_streams_tenant_rows(self, pg_app, v2_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(v2_seed["admin"].id))
        r = client.get(
            "/api/_internal/usage/export.csv",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        reader = csv.DictReader(io.StringIO(r.get_data(as_text=True)))
        rows = list(reader)
        assert len(rows) == 4
        assert {row["meter"] for row in rows} >= {
            "envelopes.prepared",
            "pdfs.sealed",
            "verifies.ok",
        }

    def test_meter_filter(self, pg_app, v2_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(v2_seed["admin"].id))
        r = client.get(
            "/api/_internal/usage/export.csv?meter=envelopes.prepared",
            headers={"Authorization": f"Bearer {token}"},
        )
        rows = list(csv.DictReader(io.StringIO(r.get_data(as_text=True))))
        assert len(rows) == 2
        assert all(row["meter"] == "envelopes.prepared" for row in rows)

    def test_since_until_bounds(self, pg_app, v2_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(v2_seed["admin"].id))
        base = v2_seed["rows"][0].recorded_at
        since = base.isoformat()
        until = (base + timedelta(minutes=30)).isoformat()
        r = client.get(
            f"/api/_internal/usage/export.csv?since={since}&until={until}",
            headers={"Authorization": f"Bearer {token}"},
        )
        rows = list(csv.DictReader(io.StringIO(r.get_data(as_text=True))))
        assert len(rows) == 1
        assert rows[0]["meter"] == "envelopes.prepared"

    def test_non_admin_forbidden(self, pg_app, v2_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(v2_seed["regular"].id))
        r = client.get(
            "/api/_internal/usage/export.csv",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    def test_max_rows_ceiling(self, pg_app, v2_seed):
        client = pg_app.test_client()
        token = create_access_token(identity=str(v2_seed["admin"].id))
        r = client.get(
            "/api/_internal/usage/export.csv?max_rows=999999",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400
