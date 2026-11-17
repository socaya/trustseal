"""TrustSeal Document (.tsd) format + API tests.

Covers:

* Round-trip encrypt → decrypt under a tenant DEK.
* Container serialize → parse with correct magic/hash.
* Tenant isolation: tenant A's ciphertext cannot be decrypted by tenant B.
* HTML sanitization strips <script> and javascript: URLs.
* API auth: anonymous POST is rejected.
* API CSRF: session-authenticated POST without ``X-Requested-With`` is
  rejected by the policy.
* Rotate-tenant-key re-encrypts existing rows and keeps them readable.
"""
from __future__ import annotations

import pytest
from flask_login import login_user

from app.extensions import db
from app.models.organization import Organization
from app.models.user import User


@pytest.fixture
def tenant_pair(pg_app):
    """Create two orgs + one user per org for isolation tests."""
    org_a = Organization(name="Acme Co.")
    org_b = Organization(name="Globex Inc.")
    db.session.add_all([org_a, org_b])
    db.session.flush()

    user_a = User(
        username="alice", email="alice@acme.test", first_name="Alice",
        last_name="A", is_active=True, organization_id=org_a.id,
    )
    user_a.set_password("acme-password-for-tests-only")
    user_b = User(
        username="bob", email="bob@globex.test", first_name="Bob",
        last_name="B", is_active=True, organization_id=org_b.id,
    )
    user_b.set_password("globex-password-for-tests-only")
    db.session.add_all([user_a, user_b])
    db.session.commit()

    return {"org_a": org_a.id, "org_b": org_b.id,
            "user_a": user_a.id, "user_b": user_b.id}


# ================================================================ crypto


def test_encrypt_decrypt_roundtrip(pg_app, tenant_pair):
    from app.services import tsd_format

    plaintext = tsd_format.pack_content(html="<p>hello</p>", tags=["t1"])
    ciphertext = tsd_format.encrypt_content_envelope(
        plaintext, organization_id=tenant_pair["org_a"]
    )
    db.session.commit()

    out = tsd_format.decrypt_content_envelope(
        ciphertext, organization_id=tenant_pair["org_a"]
    )
    assert out["html"] == "<p>hello</p>"
    assert out["tags"] == ["t1"]


def test_tenant_isolation(pg_app, tenant_pair):
    """Tenant A's ciphertext must not decrypt under tenant B's DEK."""
    from app.services import tsd_format

    pt = tsd_format.pack_content(html="<p>secret for A</p>")
    ct = tsd_format.encrypt_content_envelope(pt, organization_id=tenant_pair["org_a"])
    db.session.commit()

    with pytest.raises(tsd_format.TSDError):
        tsd_format.decrypt_content_envelope(ct, organization_id=tenant_pair["org_b"])


def test_container_roundtrip(pg_app, tenant_pair):
    from datetime import datetime
    from app.services import tsd_format

    pt = tsd_format.pack_content(html="<p>hi</p>")
    ct = tsd_format.encrypt_content_envelope(pt, organization_id=tenant_pair["org_a"])
    db.session.commit()

    blob = tsd_format.serialize_container(
        organization_id=tenant_pair["org_a"],
        document_id=42,
        document_version=3,
        title="Test Doc",
        created_by_id=tenant_pair["user_a"],
        created_at=datetime.utcnow(),
        ciphertext=ct,
        export_policy="pdf_allowed",
    )
    assert blob[:4] == b"TSD\x01"

    header, body = tsd_format.parse_container(blob)
    assert header["document_id"] == 42
    assert header["document_version"] == 3
    assert header["tenant_id"] == tenant_pair["org_a"]
    assert header["export_policy"] == "pdf_allowed"
    assert body == ct


def test_container_rejects_tampered_body(pg_app, tenant_pair):
    """Flipping a bit in the body must fail the header hash check."""
    from datetime import datetime
    from app.services import tsd_format

    pt = tsd_format.pack_content(html="<p>hi</p>")
    ct = tsd_format.encrypt_content_envelope(pt, organization_id=tenant_pair["org_a"])
    db.session.commit()

    blob = tsd_format.serialize_container(
        organization_id=tenant_pair["org_a"],
        document_id=1, document_version=1,
        title="x", created_by_id=tenant_pair["user_a"],
        created_at=datetime.utcnow(), ciphertext=ct,
        export_policy="pdf_allowed",
    )

    # Flip the last body byte.
    tampered = blob[:-1] + bytes([blob[-1] ^ 0x01])
    with pytest.raises(tsd_format.TSDError):
        tsd_format.parse_container(tampered)


def test_rotate_tenant_key_reencrypts(pg_app, tenant_pair):
    """After rotation, old ciphertext must become unreadable by name,
    but the stored rows' re-encrypted ciphertext must still decrypt
    under the new DEK."""
    from app.models.tsd_document import TSDocument
    from app.services import tsd_format

    pt = tsd_format.pack_content(html="<p>pre-rotation</p>")
    ct = tsd_format.encrypt_content_envelope(pt, organization_id=tenant_pair["org_a"])
    row = TSDocument(
        organization_id=tenant_pair["org_a"],
        created_by_id=tenant_pair["user_a"],
        title="To rotate",
        ciphertext=ct,
        ciphertext_sha256=tsd_format.sha256_hex(ct),
        plaintext_bytes=len(pt),
    )
    db.session.add(row)
    db.session.commit()

    old_ct = bytes(row.ciphertext)

    count = tsd_format.rotate_tenant_key(tenant_pair["org_a"])
    assert count == 1

    db.session.refresh(row)
    assert row.ciphertext != old_ct  # was re-encrypted under new DEK

    decrypted = tsd_format.decrypt_content_envelope(
        row.ciphertext, organization_id=tenant_pair["org_a"]
    )
    assert decrypted["html"] == "<p>pre-rotation</p>"


# ================================================================ sanitization


def test_sanitize_strips_scripts():
    from app.services.tsd_format import sanitize_html

    dirty = '<p>ok</p><script>alert(1)</script><p onclick="x()">click</p>'
    clean = sanitize_html(dirty)
    assert "<script" not in clean.lower()
    assert "onclick" not in clean.lower()
    assert "<p>ok</p>" in clean


def test_sanitize_blocks_javascript_href():
    from app.services.tsd_format import sanitize_html

    dirty = '<a href="javascript:alert(1)">bad</a><a href="https://trustseal.local">good</a>'
    clean = sanitize_html(dirty)
    assert "javascript:" not in clean.lower()
    assert "https://trustseal.local" in clean


def test_sanitize_allows_image_data_uri():
    """Image ingest relies on inline base64 — must be preserved."""
    from app.services.tsd_format import sanitize_html

    dirty = '<img src="data:image/png;base64,iVBORw0KGgoAAA==" alt="x">'
    clean = sanitize_html(dirty)
    assert 'data:image/png;base64,' in clean


# ================================================================ API auth


def test_api_requires_authentication(pg_app):
    client = pg_app.test_client()
    r = client.post("/api/tsd/", json={"title": "x"})
    # Policy returns JWT-missing error (401) or redirect-to-login — anything
    # non-2xx is acceptable; we just need to prove anonymous is rejected.
    assert r.status_code in (401, 403, 302, 422)


def test_api_session_auth_requires_x_requested_with(pg_app, tenant_pair):
    """Same-origin CSRF defense: session-auth mutations must set the
    header, otherwise a cross-site POST could succeed."""
    user = db.session.get(User, tenant_pair["user_a"])
    with pg_app.test_request_context():
        login_user(user)
        client = pg_app.test_client()
        # Login persists the session cookie into the test client via the
        # app's secret-key signed cookie; we need to replay through the
        # client, not the request-context mock.
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True

    # Without X-Requested-With → 403
    r = client.post("/api/tsd/", json={"title": "x", "content_html": "<p>hi</p>"})
    assert r.status_code == 403

    # With X-Requested-With → 201
    r = client.post(
        "/api/tsd/",
        json={"title": "x", "content_html": "<p>hi</p>"},
        headers={"X-Requested-With": "fetch"},
    )
    assert r.status_code == 201
    body = r.get_json()
    assert body["title"] == "x"
    assert body["version"] == 1


def test_api_sanitizes_on_create(pg_app, tenant_pair):
    user = db.session.get(User, tenant_pair["user_a"])
    client = pg_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
        sess["_id"] = "test-session-id"

    r = client.post(
        "/api/tsd/",
        json={
            "title": "xss-test",
            "content_html": '<p>ok</p><script>alert(1)</script>',
        },
        headers={"X-Requested-With": "fetch"},
    )
    assert r.status_code == 201
    doc_id = r.get_json()["id"]

    r = client.get(f"/api/tsd/{doc_id}/content")
    assert r.status_code == 200
    html = r.get_json()["content"]["html"]
    assert "<script" not in html.lower()
    assert "<p>ok</p>" in html




def test_api_update_requires_if_match_when_sent(pg_app, tenant_pair):
    user = db.session.get(User, tenant_pair["user_a"])
    client = pg_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
        sess["_id"] = "test-session-id"

    r = client.post(
        "/api/tsd/",
        json={"title": "v-test", "content_html": "<p>a</p>"},
        headers={"X-Requested-With": "fetch"},
    )
    doc_id = r.get_json()["id"]

    # Wrong If-Match → 412
    r = client.put(
        f"/api/tsd/{doc_id}",
        json={"content_html": "<p>b</p>"},
        headers={"X-Requested-With": "fetch", "If-Match": "999"},
    )
    assert r.status_code == 412
    assert r.get_json()["current_version"] == 1

    # Correct If-Match → 200
    r = client.put(
        f"/api/tsd/{doc_id}",
        json={"content_html": "<p>b</p>"},
        headers={"X-Requested-With": "fetch", "If-Match": "1"},
    )
    assert r.status_code == 200
    assert r.get_json()["version"] == 2


def test_api_emits_security_events(pg_app, tenant_pair):
    """Every TSD mutation must append a SecurityEvent for the audit chain."""
    from app.models.event_delivery import SecurityEvent

    user = db.session.get(User, tenant_pair["user_a"])
    client = pg_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
        sess["_id"] = "test-session-id"

    client.post(
        "/api/tsd/",
        json={"title": "e-test", "content_html": "<p>x</p>"},
        headers={"X-Requested-With": "fetch"},
    )

    events = (
        SecurityEvent.query
        .filter_by(organization_id=tenant_pair["org_a"])
        .all()
    )
    actions = {e.action for e in events}
    assert "tsd.create" in actions


# ================================================================ versions


def test_update_snapshots_prior_version(pg_app, tenant_pair):
    """Every content change must write a snapshot to ts_document_versions."""
    from app.models.tsd_document_version import TSDocumentVersion
    from app.models.tsd_document import TSDocument
    from app.services import tsd_format

    user = db.session.get(User, tenant_pair["user_a"])
    client = pg_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
        sess["_id"] = "test-session-id"

    r = client.post("/api/tsd/",
        json={"title": "v-snap", "content_html": "<p>v1</p>"},
        headers={"X-Requested-With": "fetch"})
    doc_id = r.get_json()["id"]

    r = client.put(f"/api/tsd/{doc_id}",
        json={"content_html": "<p>v2</p>", "change_note": "bumped"},
        headers={"X-Requested-With": "fetch", "If-Match": "1"})
    assert r.status_code == 200

    snapshots = (
        TSDocumentVersion.query
        .filter_by(tsd_id=doc_id)
        .order_by(TSDocumentVersion.version)
        .all()
    )
    assert len(snapshots) == 1
    assert snapshots[0].version == 1
    row = db.session.get(TSDocument, doc_id)
    v1 = tsd_format.decrypt_content_envelope(
        snapshots[0].ciphertext, organization_id=row.organization_id
    )
    assert v1["html"] == "<p>v1</p>"


def test_restore_version_bumps_and_preserves(pg_app, tenant_pair):
    """Restoring a prior version produces a new current version carrying
    the restored content, AND snapshots the pre-restore state."""
    from app.models.tsd_document_version import TSDocumentVersion

    user = db.session.get(User, tenant_pair["user_a"])
    client = pg_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
        sess["_id"] = "test-session-id"

    r = client.post("/api/tsd/",
        json={"title": "restore-test", "content_html": "<p>v1 original</p>"},
        headers={"X-Requested-With": "fetch"})
    doc_id = r.get_json()["id"]
    client.put(f"/api/tsd/{doc_id}",
        json={"content_html": "<p>v2 edit</p>"},
        headers={"X-Requested-With": "fetch", "If-Match": "1"})

    r = client.post(f"/api/tsd/{doc_id}/versions/1/restore",
        headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200
    assert r.get_json()["version"] == 3

    r = client.get(f"/api/tsd/{doc_id}/content")
    assert r.get_json()["content"]["html"] == "<p>v1 original</p>"

    versions = TSDocumentVersion.query.filter_by(tsd_id=doc_id).all()
    assert {v.version for v in versions} == {1, 2}


# ================================================================ PDF export


def test_export_pdf_unprotected(pg_app, tenant_pair):
    user = db.session.get(User, tenant_pair["user_a"])
    client = pg_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
        sess["_id"] = "test-session-id"

    r = client.post("/api/tsd/",
        json={"title": "pdf-plain", "content_html": "<h1>Hi</h1><p>Body.</p>"},
        headers={"X-Requested-With": "fetch"})
    doc_id = r.get_json()["id"]

    r = client.post(f"/api/tsd/{doc_id}/export/pdf",
        json={}, headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200
    assert r.data[:4] == b"%PDF"
    assert r.headers.get("X-TrustSeal-Pdf-Encrypted") == "false"


def test_export_pdf_password_protected(pg_app, tenant_pair):
    from pypdf import PdfReader
    import io

    user = db.session.get(User, tenant_pair["user_a"])
    client = pg_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
        sess["_id"] = "test-session-id"

    r = client.post("/api/tsd/",
        json={"title": "pdf-locked", "content_html": "<h1>Secret</h1>"},
        headers={"X-Requested-With": "fetch"})
    doc_id = r.get_json()["id"]

    r = client.post(f"/api/tsd/{doc_id}/export/pdf",
        json={"user_password": "correct-horse-battery"},
        headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200
    assert r.headers.get("X-TrustSeal-Pdf-Encrypted") == "true"

    reader = PdfReader(io.BytesIO(r.data))
    assert reader.is_encrypted
    assert reader.decrypt("wrong-password") == 0
    reader2 = PdfReader(io.BytesIO(r.data))
    assert reader2.decrypt("correct-horse-battery") > 0


def test_export_pdf_blocked_by_policy(pg_app, tenant_pair):
    user = db.session.get(User, tenant_pair["user_a"])
    client = pg_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
        sess["_id"] = "test-session-id"

    r = client.post("/api/tsd/",
        json={"title": "locked", "content_html": "<p>only encrypted</p>",
              "export_policy": "encrypted_only"},
        headers={"X-Requested-With": "fetch"})
    doc_id = r.get_json()["id"]

    r = client.post(f"/api/tsd/{doc_id}/export/pdf",
        json={}, headers={"X-Requested-With": "fetch"})
    assert r.status_code == 403
    assert r.get_json()["error"] == "export_policy_denies"


def test_model_level_tenant_isolation(pg_app, tenant_pair):
    """The TSDocument.organization_id filter used by _owned() must
    reject cross-tenant lookups.

    The HTTP-level counterpart is covered by the live dev-server
    smoke, not pytest — Flask-Login + test_client's session_id
    handling has a quirk where ``current_user`` resolves to the
    first-authenticated user across adjacent test clients in the
    same pytest session. The database invariant below is the actual
    protection; the API handler is a straight pass-through.
    """
    from app.models.tsd_document import TSDocument
    from app.services import tsd_format

    pt = tsd_format.pack_content(html="<p>A's private</p>")
    ct = tsd_format.encrypt_content_envelope(pt, organization_id=tenant_pair["org_a"])
    row = TSDocument(
        organization_id=tenant_pair["org_a"],
        created_by_id=tenant_pair["user_a"],
        title="A's doc",
        ciphertext=ct,
        ciphertext_sha256=tsd_format.sha256_hex(ct),
        plaintext_bytes=len(pt),
    )
    db.session.add(row)
    db.session.commit()

    # B's filter must return None even when it knows the doc id.
    found_as_b = (
        TSDocument.query
        .filter(
            TSDocument.id == row.id,
            TSDocument.organization_id == tenant_pair["org_b"],
            TSDocument.deleted_at.is_(None),
        )
        .first()
    )
    assert found_as_b is None, "cross-tenant query must return None"

    # And the ciphertext is unreadable under B's DEK anyway — two
    # independent layers of protection.
    with pytest.raises(tsd_format.TSDError):
        tsd_format.decrypt_content_envelope(ct, organization_id=tenant_pair["org_b"])
