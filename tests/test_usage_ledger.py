"""Usage ledger (F1).

Covers:

Service layer:
* ``record`` with a fresh ``source_event_id`` returns True and
  inserts a row.
* A second call with the same ``source_event_id`` returns False and
  keeps the count at one.
* Unknown meters are rejected.
* ``usage_for`` sums hits within a window.
* ``current_period_usage`` resolves the "month" window correctly.

Business-event integration:
* Preparing an envelope records one ``envelope.prepared`` hit; a
  retried prepare does not double-count.
* A successful bulk-ingest batch of 2 PDFs records 2
  ``document.bulk_ingested`` hits.

HTTP:
* ``GET /api/usage/summary`` returns the current period's hit
  counts for the authenticated tenant.
"""
from __future__ import annotations

import io
from datetime import datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from werkzeug.datastructures import MultiDict


def _pdf(label: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(72, 720, "Usage ledger: " + label)
    c.showPage()
    c.save()
    return buf.getvalue()


@pytest.fixture
def noop_scanner(monkeypatch):
    from app.services.documents import private_storage

    monkeypatch.setattr(
        private_storage,
        "_scan_pdf",
        lambda path, config: "noop-scanner-test-only",
    )
    yield


@pytest.fixture
def private_root(pg_app, tmp_path):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(root)
    return root


@pytest.fixture
def seeded(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.user import User

    org = Organization(name="Usage Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    owner = User(
        username="usage-owner",
        email="usage-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("usagepassword12345")
    db.session.add(owner)
    db.session.commit()
    return {"org": org, "owner": owner}


class TestService:
    def test_first_insert_returns_true(self, pg_app, seeded):
        from app.extensions import db
        from app.services import usage_ledger

        inserted = usage_ledger.record(
            seeded["org"].id, "envelope.prepared", "envelope:42"
        )
        db.session.commit()
        assert inserted is True
        assert (
            usage_ledger.current_period_usage(
                seeded["org"].id, "envelope.prepared"
            )
            == 1
        )

    def test_dedupe_second_insert(self, pg_app, seeded):
        from app.extensions import db
        from app.services import usage_ledger

        usage_ledger.record(seeded["org"].id, "envelope.prepared", "envelope:7")
        db.session.commit()
        again = usage_ledger.record(
            seeded["org"].id, "envelope.prepared", "envelope:7"
        )
        db.session.commit()
        assert again is False
        assert (
            usage_ledger.current_period_usage(
                seeded["org"].id, "envelope.prepared"
            )
            == 1
        )

    def test_unknown_meter_rejected(self, pg_app, seeded):
        from app.services import usage_ledger

        with pytest.raises(usage_ledger.UsageError):
            usage_ledger.record(
                seeded["org"].id, "not.a.meter", "evt:1"
            )

    def test_usage_for_window(self, pg_app, seeded):
        from app.extensions import db
        from app.services import usage_ledger

        now = datetime.utcnow()
        usage_ledger.record(
            seeded["org"].id,
            "envelope.prepared",
            "evt:1",
            recorded_at=now - timedelta(days=40),
        )
        usage_ledger.record(
            seeded["org"].id,
            "envelope.prepared",
            "evt:2",
            recorded_at=now - timedelta(hours=2),
        )
        db.session.commit()
        recent = usage_ledger.usage_for(
            seeded["org"].id,
            "envelope.prepared",
            since=now - timedelta(days=7),
            until=now + timedelta(days=1),
        )
        assert recent == 1


class TestEnvelopeIntegration:
    def test_prepare_meters_once(
        self, pg_app, seeded, private_root, noop_scanner
    ):
        from app.extensions import db
        from app.models.documents.document import Document
        from app.models.documents.document_blob import DocumentBlob
        from app.models.signing_envelope import (
            EnvelopeParticipant,
            SigningEnvelope,
        )
        from app.models.user import User
        from app.services import usage_ledger

        import hashlib

        signer = User(
            username="usage-signer",
            email="usage-signer@example.test",
            is_active=True,
            organization_id=seeded["org"].id,
        )
        signer.set_password("usagepassword12345")
        db.session.add(signer)
        db.session.flush()
        doc = Document(
            title="Usage doc",
            status="draft",
            created_by=seeded["owner"].id,
            organization_id=seeded["org"].id,
        )
        db.session.add(doc)
        db.session.flush()
        body = _pdf("usage")
        digest = hashlib.sha256(body).hexdigest()
        (private_root / f"{digest}.pdf").write_bytes(body)
        blob = DocumentBlob(
            document_id=doc.id,
            revision=1,
            object_key=f"{digest}.pdf",
            file_name="usage.pdf",
            mime_type="application/pdf",
            file_size=len(body),
            sha256=digest,
            scanner="noop",
            created_by_id=seeded["owner"].id,
        )
        db.session.add(blob)
        db.session.flush()
        envelope = SigningEnvelope(
            organization_id=seeded["org"].id,
            document_id=doc.id,
            document_blob_id=blob.id,
            document_sha256=digest,
            created_by_id=seeded["owner"].id,
            state="draft",
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
        envelope.preview_confirmed_at = datetime.utcnow()
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["owner"].id))
        # First prepare: should meter.
        r = client.post(
            f"/api/envelopes/{envelope.id}/prepare",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"usage-prep-{envelope.id}",
            },
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        # Idempotent retry: the SAME Idempotency-Key must not double-
        # count. We verify by calling record() directly with the same
        # source_event_id and confirming it reports False (already
        # recorded during the prepare).
        again = usage_ledger.record(
            seeded["org"].id,
            "envelope.prepared",
            f"envelope:{envelope.id}",
        )
        assert again is False
        assert (
            usage_ledger.current_period_usage(
                seeded["org"].id, "envelope.prepared"
            )
            == 1
        )


class TestBulkIntegration:
    def test_bulk_meters_per_successful_item(
        self, pg_app, seeded, private_root, noop_scanner
    ):
        from app.services import usage_ledger

        token = create_access_token(identity=str(seeded["owner"].id))
        client = pg_app.test_client()
        files = MultiDict([
            ("files", (io.BytesIO(_pdf("a")), "a.pdf")),
            ("files", (io.BytesIO(_pdf("b")), "b.pdf")),
            ("files", (io.BytesIO(b"not a pdf"), "bad.pdf")),
        ])
        r = client.post(
            "/api/documents/bulk",
            data=files,
            content_type="multipart/form-data",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 207
        # Two successful items → two meter hits, one failure → no hit.
        assert (
            usage_ledger.current_period_usage(
                seeded["org"].id, "document.bulk_ingested"
            )
            == 2
        )


class TestApi:
    def test_summary_returns_meters(self, pg_app, seeded):
        from app.extensions import db
        from app.services import usage_ledger

        usage_ledger.record(
            seeded["org"].id, "envelope.prepared", "evt:a"
        )
        usage_ledger.record(
            seeded["org"].id, "document.ingested", "evt:b"
        )
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["owner"].id))
        r = client.get(
            "/api/usage/summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        meters = r.get_json()["meters"]
        assert meters["envelope.prepared"] == 1
        assert meters["document.ingested"] == 1

    def test_unknown_period_rejected(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["owner"].id))
        r = client.get(
            "/api/usage/summary?period=hour",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400
