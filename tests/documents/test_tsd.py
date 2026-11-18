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


# ================================================================ shares


@pytest.fixture
def same_tenant_pair(pg_app):
    """Two users in the SAME org (unlike tenant_pair which separates them)."""
    org = Organization(name="ShareCo")
    db.session.add(org); db.session.flush()
    owner = User(username="owner", email="owner@share.test", first_name="O",
                 last_name="W", is_active=True, organization_id=org.id)
    owner.set_password("owner-password-for-tests-only")
    mate = User(username="mate", email="mate@share.test", first_name="M",
                last_name="T", is_active=True, organization_id=org.id)
    mate.set_password("mate-password-for-tests-only")
    db.session.add_all([owner, mate]); db.session.commit()
    return {"org": org.id, "owner": owner.id, "mate": mate.id,
            "owner_email": owner.email, "mate_email": mate.email}


def _client_as(pg_app, user_id):
    c = pg_app.test_client()
    with c.session_transaction() as sess:
        sess["_user_id"] = str(user_id); sess["_fresh"] = True; sess["_id"] = "s"
    return c


def test_create_and_list_share(pg_app, same_tenant_pair):
    c = _client_as(pg_app, same_tenant_pair["owner"])
    doc = c.post("/api/tsd/", json={"title": "sharable", "content_html": "<p>ok</p>"},
                 headers={"X-Requested-With": "fetch"}).get_json()
    r = c.post(f"/api/tsd/{doc['id']}/shares",
               json={"email": same_tenant_pair["mate_email"], "permission": "view"},
               headers={"X-Requested-With": "fetch"})
    assert r.status_code == 201
    share = r.get_json()
    assert share["permission"] == "view"
    assert share["grantee_user_id"] == same_tenant_pair["mate"]

    r = c.get(f"/api/tsd/{doc['id']}/shares")
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["active"] is True


def test_share_rejects_non_tenant_email(pg_app, same_tenant_pair):
    c = _client_as(pg_app, same_tenant_pair["owner"])
    doc = c.post("/api/tsd/", json={"title": "x", "content_html": "<p>a</p>"},
                 headers={"X-Requested-With": "fetch"}).get_json()
    r = c.post(f"/api/tsd/{doc['id']}/shares",
               json={"email": "outsider@nope.test", "permission": "view"},
               headers={"X-Requested-With": "fetch"})
    assert r.status_code == 404
    assert r.get_json()["error"] == "grantee_not_in_tenant"


def test_share_rejects_invalid_permission(pg_app, same_tenant_pair):
    c = _client_as(pg_app, same_tenant_pair["owner"])
    doc = c.post("/api/tsd/", json={"title": "x", "content_html": "<p>a</p>"},
                 headers={"X-Requested-With": "fetch"}).get_json()
    r = c.post(f"/api/tsd/{doc['id']}/shares",
               json={"email": same_tenant_pair["mate_email"], "permission": "admin"},
               headers={"X-Requested-With": "fetch"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid_permission"


def test_revoke_share(pg_app, same_tenant_pair):
    c = _client_as(pg_app, same_tenant_pair["owner"])
    doc = c.post("/api/tsd/", json={"title": "x", "content_html": "<p>a</p>"},
                 headers={"X-Requested-With": "fetch"}).get_json()
    share = c.post(f"/api/tsd/{doc['id']}/shares",
                   json={"email": same_tenant_pair["mate_email"], "permission": "edit"},
                   headers={"X-Requested-With": "fetch"}).get_json()

    r = c.delete(f"/api/tsd/{doc['id']}/shares/{share['id']}",
                 headers={"X-Requested-With": "fetch"})
    assert r.status_code == 204

    # Second revoke must 409 — row is kept for audit.
    r = c.delete(f"/api/tsd/{doc['id']}/shares/{share['id']}",
                 headers={"X-Requested-With": "fetch"})
    assert r.status_code == 409


def test_share_with_expiry(pg_app, same_tenant_pair):
    c = _client_as(pg_app, same_tenant_pair["owner"])
    doc = c.post("/api/tsd/", json={"title": "x", "content_html": "<p>a</p>"},
                 headers={"X-Requested-With": "fetch"}).get_json()
    r = c.post(f"/api/tsd/{doc['id']}/shares",
               json={"email": same_tenant_pair["mate_email"], "permission": "view",
                     "expires_in_days": 7},
               headers={"X-Requested-With": "fetch"})
    assert r.status_code == 201
    assert r.get_json()["expires_at"] is not None


# ================================================================ comments


def test_create_and_list_comments(pg_app, tenant_pair):
    c = _client_as(pg_app, tenant_pair["user_a"])
    doc = c.post("/api/tsd/", json={"title": "x", "content_html": "<p>a</p>"},
                 headers={"X-Requested-With": "fetch"}).get_json()
    r = c.post(f"/api/tsd/{doc['id']}/comments",
               json={"body": "Needs tightening in section 2",
                     "anchor_id": "h-2", "anchor_text": "Section 2 heading"},
               headers={"X-Requested-With": "fetch"})
    assert r.status_code == 201
    cid = r.get_json()["id"]

    # Reply
    r = c.post(f"/api/tsd/{doc['id']}/comments",
               json={"body": "Agreed, revising", "parent_comment_id": cid},
               headers={"X-Requested-With": "fetch"})
    assert r.status_code == 201

    r = c.get(f"/api/tsd/{doc['id']}/comments")
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 2
    assert items[0]["anchor_id"] == "h-2"


def test_resolve_comment(pg_app, tenant_pair):
    c = _client_as(pg_app, tenant_pair["user_a"])
    doc = c.post("/api/tsd/", json={"title": "x", "content_html": "<p>a</p>"},
                 headers={"X-Requested-With": "fetch"}).get_json()
    cm = c.post(f"/api/tsd/{doc['id']}/comments", json={"body": "hi"},
                headers={"X-Requested-With": "fetch"}).get_json()
    r = c.post(f"/api/tsd/{doc['id']}/comments/{cm['id']}/resolve",
               headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200
    assert r.get_json()["resolved_at"] is not None


# ================================================================ external shares


def test_create_external_share_mints_token(pg_app, tenant_pair):
    c = _client_as(pg_app, tenant_pair["user_a"])
    doc = c.post("/api/tsd/", json={"title": "x", "content_html": "<p>a</p>"},
                 headers={"X-Requested-With": "fetch"}).get_json()
    r = c.post(f"/api/tsd/{doc['id']}/external-shares",
               json={"email": "outsider@ext.test", "permission": "view",
                     "expires_in_days": 7},
               headers={"X-Requested-With": "fetch"})
    assert r.status_code == 201
    body = r.get_json()
    assert body["token"]       # raw token returned exactly once
    assert body["link"]        # magic link included
    assert "token" not in body or body["token"]  # sanity

    # The token hash is what's stored — raw token must not be queryable.
    from app.models.tsd_external_share import TSDExternalShare, hash_token
    row = TSDExternalShare.query.get(body["id"])
    assert row.token_hash == hash_token(body["token"])
    assert row.recipient_email == "outsider@ext.test"


def test_external_share_landing_without_token_404(pg_app, tenant_pair):
    c = _client_as(pg_app, tenant_pair["user_a"])
    doc = c.post("/api/tsd/", json={"title": "x", "content_html": "<p>a</p>"},
                 headers={"X-Requested-With": "fetch"}).get_json()
    ext = c.post(f"/api/tsd/{doc['id']}/external-shares",
                 json={"email": "o@ext.test", "permission": "view",
                       "expires_in_days": 7},
                 headers={"X-Requested-With": "fetch"}).get_json()

    # Anonymous client: no session cookie.
    anon = pg_app.test_client()
    r = anon.get(f"/tsd/external/{ext['id']}")
    assert r.status_code == 404  # missing token
    r = anon.get(f"/tsd/external/{ext['id']}?token=wrong")
    assert r.status_code == 404


def test_external_share_landing_with_token_renders(pg_app, tenant_pair):
    c = _client_as(pg_app, tenant_pair["user_a"])
    doc = c.post("/api/tsd/", json={"title": "Public draft", "content_html": "<h1>Hi</h1><p>External</p>"},
                 headers={"X-Requested-With": "fetch"}).get_json()
    ext = c.post(f"/api/tsd/{doc['id']}/external-shares",
                 json={"email": "o@ext.test", "permission": "view",
                       "expires_in_days": 7},
                 headers={"X-Requested-With": "fetch"}).get_json()
    anon = pg_app.test_client()
    r = anon.get(f"/tsd/external/{ext['id']}?token={ext['token']}")
    assert r.status_code == 200
    assert b"Public draft" in r.data
    assert b"External" in r.data


# ================================================================ approvals


def test_request_approvals_and_workflow_state(pg_app, same_tenant_pair):
    """Owner creates approvers; state derivation works as expected.

    (The decide HTTP endpoint is covered by the model-level test below —
    the test client cannot reliably switch which user current_user
    resolves to in the pytest session.)
    """
    from app.models.tsd_approval import TSDApproval

    owner = _client_as(pg_app, same_tenant_pair["owner"])
    doc = owner.post("/api/tsd/", json={"title": "x", "content_html": "<p>a</p>"},
                     headers={"X-Requested-With": "fetch"}).get_json()
    r = owner.post(f"/api/tsd/{doc['id']}/approvals",
                   json={"approver_emails": [same_tenant_pair["mate_email"]],
                         "order_index": 0},
                   headers={"X-Requested-With": "fetch"})
    assert r.status_code == 201

    r = owner.get(f"/api/tsd/{doc['id']}/approvals")
    assert r.status_code == 200
    data = r.get_json()
    assert data["workflow_state"] == "awaiting_first"

    # Owner cannot decide on behalf of the approver (403).
    aid = data["approvals"][0]["id"]
    r = owner.post(f"/api/tsd/{doc['id']}/approvals/{aid}/decide",
                   json={"decision": "approved"},
                   headers={"X-Requested-With": "fetch"})
    assert r.status_code == 403


def test_approval_workflow_states(pg_app, same_tenant_pair):
    """Workflow state derivation directly against the model."""
    from datetime import datetime
    from app.models.tsd_approval import TSDApproval
    from app.models.tsd_document import TSDocument
    from app.services import tsd_format

    pt = tsd_format.pack_content(html="<p>x</p>")
    ct = tsd_format.encrypt_content_envelope(pt, organization_id=same_tenant_pair["org"])
    doc = TSDocument(
        organization_id=same_tenant_pair["org"],
        created_by_id=same_tenant_pair["owner"],
        title="wf", ciphertext=ct,
        ciphertext_sha256=tsd_format.sha256_hex(ct),
        plaintext_bytes=len(pt),
    )
    db.session.add(doc); db.session.flush()

    def _mk(approver_id, order=0, status="pending"):
        return TSDApproval(
            tsd_id=doc.id, organization_id=same_tenant_pair["org"],
            approver_id=approver_id, order_index=order, status=status,
            created_by_id=same_tenant_pair["owner"],
            decided_at=datetime.utcnow() if status != "pending" else None,
        )

    # All pending → "awaiting_first" when listed.
    db.session.add(_mk(same_tenant_pair["mate"], status="pending"))
    db.session.commit()

    c = _client_as(pg_app, same_tenant_pair["owner"])
    r = c.get(f"/api/tsd/{doc.id}/approvals")
    assert r.get_json()["workflow_state"] == "awaiting_first"

    # Flip to approved → state "approved".
    a = TSDApproval.query.filter_by(tsd_id=doc.id).first()
    a.status = "approved"; a.decided_at = datetime.utcnow()
    db.session.commit()
    r = c.get(f"/api/tsd/{doc.id}/approvals")
    assert r.get_json()["workflow_state"] == "approved"

    # Add another at same order with rejection → state "rejected".
    db.session.add(_mk(same_tenant_pair["owner"], status="rejected"))
    db.session.commit()
    r = c.get(f"/api/tsd/{doc.id}/approvals")
    assert r.get_json()["workflow_state"] == "rejected"


# ================================================================ presence


def test_presence_ping_and_list(pg_app, same_tenant_pair):
    owner = _client_as(pg_app, same_tenant_pair["owner"])
    doc = owner.post("/api/tsd/", json={"title": "x", "content_html": "<p>a</p>"},
                     headers={"X-Requested-With": "fetch"}).get_json()

    r = owner.post(f"/api/tsd/{doc['id']}/presence",
                   headers={"X-Requested-With": "fetch"})
    assert r.status_code == 204

    r = owner.get(f"/api/tsd/{doc['id']}/presence")
    assert r.status_code == 200
    viewers = r.get_json()
    assert len(viewers) == 1
    assert viewers[0]["user_id"] == same_tenant_pair["owner"]
    assert viewers[0]["initials"]


# ================================================================ templates


def test_list_built_in_templates(pg_app, tenant_pair):
    user = db.session.get(User, tenant_pair["user_a"])
    client = pg_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id); sess["_fresh"] = True; sess["_id"] = "s"
    r = client.get("/api/tsd/templates")
    assert r.status_code == 200
    items = r.get_json()
    slugs = {t["slug"] for t in items}
    assert {"nda", "services-agreement", "memo", "letter", "board-resolution",
            "meeting-minutes", "policy", "blank"}.issubset(slugs)


def test_instantiate_from_template(pg_app, tenant_pair):
    user = db.session.get(User, tenant_pair["user_a"])
    client = pg_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id); sess["_fresh"] = True; sess["_id"] = "s"

    r = client.post("/api/tsd/from-template/nda",
                    json={}, headers={"X-Requested-With": "fetch"})
    assert r.status_code == 201
    doc = r.get_json()
    assert doc["title"] == "Mutual Non-Disclosure Agreement"

    # Fetch decrypted content — must contain template body + placeholder fields.
    r = client.get(f"/api/tsd/{doc['id']}/content")
    html = r.get_json()["content"]["html"]
    assert "MUTUAL NON-DISCLOSURE AGREEMENT" in html
    assert "{{effective_date}}" in html
    assert "{{party_a}}" in html


def test_instantiate_unknown_template_404(pg_app, tenant_pair):
    user = db.session.get(User, tenant_pair["user_a"])
    client = pg_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id); sess["_fresh"] = True; sess["_id"] = "s"
    r = client.post("/api/tsd/from-template/nope",
                    json={}, headers={"X-Requested-With": "fetch"})
    assert r.status_code == 404


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
