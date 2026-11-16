"""Bulk document ingestion (D3).

Covers:

* ``POST /api/documents/bulk`` with three PDFs creates three
  Documents + three DocumentBlobs and returns a batch summary.
* Mixed batch: two valid PDFs + one non-PDF payload — the non-PDF
  is reported as ``failed`` with an error_code, the valid files
  land as ``succeeded`` with document_id + blob_id. Response is 207.
* Limit of 25 files per batch is enforced (413).
* ``GET /api/documents/bulk/<id>`` returns the persisted batch for
  polling retries.
* Cross-tenant access to a batch returns 404.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from flask_jwt_extended import create_access_token
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from werkzeug.datastructures import MultiDict


def _pdf(name: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(72, 720, "Bulk ingest: %s" % name)
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
def actors(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.user import User

    def mk_org(name):
        o = Organization(name=name, type="company")
        db.session.add(o)
        db.session.flush()
        return o

    org_a = mk_org("Bulk Tenant")
    org_b = mk_org("Bulk Foreign")

    def mk_user(username, email, org):
        u = User(
            username=username,
            email=email,
            is_active=True,
            organization_id=org.id,
        )
        u.set_password("bulkpassword12345")
        db.session.add(u)
        db.session.flush()
        return u

    owner = mk_user("bulk-owner", "bulk-owner@example.test", org_a)
    foreign = mk_user("bulk-foreign", "bulk-foreign@example.test", org_b)
    db.session.commit()
    return {"org_a": org_a, "org_b": org_b, "owner": owner, "foreign": foreign}


class TestBulkIngest:
    def test_three_valid_pdfs_land(
        self, pg_app, actors, private_root, noop_scanner
    ):
        from app.extensions import db
        from app.models.documents.document import Document
        from app.models.documents.document_blob import DocumentBlob

        token = create_access_token(identity=str(actors["owner"].id))
        client = pg_app.test_client()
        files = MultiDict([
            ("files", (io.BytesIO(_pdf("a")), "alpha.pdf")),
            ("files", (io.BytesIO(_pdf("b")), "beta.pdf")),
            ("files", (io.BytesIO(_pdf("c")), "gamma.pdf")),
        ])
        r = client.post(
            "/api/documents/bulk",
            data=files,
            content_type="multipart/form-data",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201, r.get_data(as_text=True)
        body = r.get_json()
        assert body["batch"]["item_count"] == 3
        assert body["batch"]["success_count"] == 3
        assert body["batch"]["failure_count"] == 0
        assert all(it["status"] == "succeeded" for it in body["items"])
        db.session.expire_all()
        created_docs = Document.query.filter_by(
            organization_id=actors["org_a"].id
        ).count()
        assert created_docs == 3
        assert DocumentBlob.query.count() == 3

    def test_mixed_batch_returns_207(
        self, pg_app, actors, private_root, noop_scanner
    ):
        token = create_access_token(identity=str(actors["owner"].id))
        client = pg_app.test_client()
        files = MultiDict([
            ("files", (io.BytesIO(_pdf("good-1")), "good-1.pdf")),
            ("files", (io.BytesIO(b"not a pdf at all"), "bad.pdf")),
            ("files", (io.BytesIO(_pdf("good-2")), "good-2.pdf")),
        ])
        r = client.post(
            "/api/documents/bulk",
            data=files,
            content_type="multipart/form-data",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 207, r.get_data(as_text=True)
        body = r.get_json()
        assert body["batch"]["success_count"] == 2
        assert body["batch"]["failure_count"] == 1
        failed = [it for it in body["items"] if it["status"] == "failed"]
        assert len(failed) == 1
        assert failed[0]["filename"] == "bad.pdf"
        assert failed[0]["error_code"] == "ingestion_error"

    def test_limit_25_enforced(
        self, pg_app, actors, private_root, noop_scanner
    ):
        token = create_access_token(identity=str(actors["owner"].id))
        client = pg_app.test_client()
        files = MultiDict([
            ("files", (io.BytesIO(_pdf(f"doc{i}")), f"doc{i}.pdf"))
            for i in range(26)
        ])
        r = client.post(
            "/api/documents/bulk",
            data=files,
            content_type="multipart/form-data",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 413

    def test_get_batch_status(
        self, pg_app, actors, private_root, noop_scanner
    ):
        from app.extensions import db

        token = create_access_token(identity=str(actors["owner"].id))
        client = pg_app.test_client()
        r = client.post(
            "/api/documents/bulk",
            data=MultiDict([("files", (io.BytesIO(_pdf("one")), "one.pdf"))]),
            content_type="multipart/form-data",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        batch_id = r.get_json()["batch"]["id"]
        r2 = client.get(
            f"/api/documents/bulk/{batch_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r2.status_code == 200
        body = r2.get_json()
        assert body["batch"]["id"] == batch_id
        assert body["batch"]["success_count"] == 1

    def test_foreign_batch_is_404(
        self, pg_app, actors, private_root, noop_scanner
    ):
        from app.extensions import db

        token = create_access_token(identity=str(actors["owner"].id))
        client = pg_app.test_client()
        r = client.post(
            "/api/documents/bulk",
            data=MultiDict([("files", (io.BytesIO(_pdf("mine")), "mine.pdf"))]),
            content_type="multipart/form-data",
            headers={"Authorization": f"Bearer {token}"},
        )
        batch_id = r.get_json()["batch"]["id"]
        foreign_token = create_access_token(identity=str(actors["foreign"].id))
        r = client.get(
            f"/api/documents/bulk/{batch_id}",
            headers={"Authorization": f"Bearer {foreign_token}"},
        )
        assert r.status_code == 404
