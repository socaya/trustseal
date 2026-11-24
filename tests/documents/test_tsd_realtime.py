"""Tests for the realtime awareness channel.

These exercise the pure-Python helpers in :mod:`app.services.tsd_realtime`
— stable colour mapping, display helpers, and the access check that
every socket event reuses from the HTTP ``_owned`` logic.

The full socket round-trip is covered by the live smoke script in
docs/TSD_Real_Time_Collab_Plan.md. Exercising Socket.IO in-process
against the Flask test client requires running the Werkzeug dev server
in a thread and a real Socket.IO client, which costs more harness than
the value it buys here.
"""
from __future__ import annotations

import pytest

from app.extensions import db
from app.models.organization import Organization
from app.models.user import User


@pytest.fixture
def realtime_tenant(pg_app):
    org = Organization(name="RT Co.")
    db.session.add(org); db.session.flush()
    alice = User(username="alice-rt", email="alice@rt.test", first_name="Alice",
                 last_name="RT", is_active=True, organization_id=org.id)
    alice.set_password("rt-password-for-tests-only")
    bob = User(username="bob-rt", email="bob@rt.test", first_name="Bob",
               last_name="RT", is_active=True, organization_id=org.id)
    bob.set_password("rt-password-for-tests-only")
    db.session.add_all([alice, bob]); db.session.commit()
    return {"org": org.id, "alice": alice, "bob": bob}


def test_color_is_stable_per_user(realtime_tenant):
    from app.services.tsd_realtime import _color_for
    c1 = _color_for(realtime_tenant["alice"].id)
    c2 = _color_for(realtime_tenant["alice"].id)
    c3 = _color_for(realtime_tenant["bob"].id)
    assert c1 == c2
    assert c1 != c3
    assert c1.startswith("hsl(")


def test_user_payload_has_identity_fields(realtime_tenant):
    from app.services.tsd_realtime import _user_payload
    p = _user_payload(realtime_tenant["alice"])
    assert set(p.keys()) >= {"user_id", "name", "email", "initials", "color"}
    assert p["user_id"] == realtime_tenant["alice"].id
    assert p["email"] == "alice@rt.test"
    assert p["initials"] == "AR"


def test_can_access_matches_owner(realtime_tenant):
    from app.services import tsd_format
    from app.services.tsd_realtime import _can_access
    from app.models.tsd_document import TSDocument

    pt = tsd_format.pack_content(html="<p>x</p>")
    ct = tsd_format.encrypt_content_envelope(pt, organization_id=realtime_tenant["org"])
    doc = TSDocument(
        organization_id=realtime_tenant["org"],
        created_by_id=realtime_tenant["alice"].id,
        title="rt-access", ciphertext=ct,
        ciphertext_sha256=tsd_format.sha256_hex(ct),
        plaintext_bytes=len(pt),
    )
    db.session.add(doc); db.session.commit()

    assert _can_access(realtime_tenant["alice"], doc.id) is True
    assert _can_access(realtime_tenant["bob"], doc.id) is True   # same tenant


def test_crdt_session_bootstraps_from_tsd(pg_app, realtime_tenant):
    """A new CrdtSession for an existing TSD must remember the current
    HTML so later snapshots fall back to it when the client hasn't yet
    pushed a structured ProseMirror update."""
    from app.services import tsd_format
    from app.services.tsd_realtime import _get_or_create_session, _release_session, _DOC_CACHE
    from app.models.tsd_document import TSDocument

    pt = tsd_format.pack_content(html="<h1>Hello CRDT</h1>")
    ct = tsd_format.encrypt_content_envelope(pt, organization_id=realtime_tenant["org"])
    doc = TSDocument(
        organization_id=realtime_tenant["org"],
        created_by_id=realtime_tenant["alice"].id,
        title="crdt-boot", ciphertext=ct,
        ciphertext_sha256=tsd_format.sha256_hex(ct),
        plaintext_bytes=len(pt),
    )
    db.session.add(doc); db.session.commit()

    sess = _get_or_create_session(doc.id)
    try:
        assert "<h1>Hello CRDT</h1>" in sess.current_html()
    finally:
        _release_session(doc.id)
        _DOC_CACHE.pop(doc.id, None)


def test_crdt_session_snapshots_pm_fragment(pg_app, realtime_tenant):
    """Snapshotting a session with an initial-HTML fallback must write
    that HTML back into the TSD ciphertext and bump the version."""
    from app.services import tsd_format
    from app.services.tsd_realtime import _get_or_create_session, _snapshot_session, _DOC_CACHE
    from app.models.tsd_document import TSDocument

    pt = tsd_format.pack_content(html="<p>start</p>")
    ct = tsd_format.encrypt_content_envelope(pt, organization_id=realtime_tenant["org"])
    doc = TSDocument(
        organization_id=realtime_tenant["org"],
        created_by_id=realtime_tenant["alice"].id,
        title="crdt-snap", ciphertext=ct,
        ciphertext_sha256=tsd_format.sha256_hex(ct),
        plaintext_bytes=len(pt),
    )
    db.session.add(doc); db.session.commit()
    original_version = doc.version

    sess = _get_or_create_session(doc.id)
    try:
        # Manually mutate the bootstrap HTML and mark dirty — simulates
        # a future state where the fragment carries the edited content.
        sess._initial_html = "<p>start</p><p>appended by crdt</p>"
        sess.dirty = True
        wrote = _snapshot_session(sess, force=True)
        assert wrote is True

        db.session.refresh(doc)
        assert doc.version == original_version + 1
        decrypted = tsd_format.decrypt_content_envelope(
            doc.ciphertext, organization_id=doc.organization_id
        )
        assert "appended by crdt" in decrypted["html"]
    finally:
        _DOC_CACHE.pop(doc.id, None)


def test_can_access_denies_outsider(realtime_tenant):
    from app.services import tsd_format
    from app.services.tsd_realtime import _can_access
    from app.models.tsd_document import TSDocument
    other_org = Organization(name="Outsider Co.")
    db.session.add(other_org); db.session.flush()
    outsider = User(username="out", email="out@x.test", first_name="O",
                    last_name="X", is_active=True, organization_id=other_org.id)
    outsider.set_password("outsider-password-for-tests-only")
    db.session.add(outsider)

    pt = tsd_format.pack_content(html="<p>x</p>")
    ct = tsd_format.encrypt_content_envelope(pt, organization_id=realtime_tenant["org"])
    doc = TSDocument(
        organization_id=realtime_tenant["org"],
        created_by_id=realtime_tenant["alice"].id,
        title="rt-access-out", ciphertext=ct,
        ciphertext_sha256=tsd_format.sha256_hex(ct),
        plaintext_bytes=len(pt),
    )
    db.session.add(doc); db.session.commit()

    assert _can_access(outsider, doc.id) is False


def test_crdt_snapshot_preserves_persisted_stamps_and_attested_signatures(pg_app, realtime_tenant):
    """CRDT text snapshots must preserve .tsd-persisted-marks (stamps & attested signatures)."""
    from datetime import datetime, timedelta
    from app.models.esignature import SignatureProfile
    from app.models.signature_governance import SignatureUsageLog
    from app.models.tsd_document import TSDocument
    from app.services import tsd_format
    from app.services.signature_attestations import issue_signature_attestation
    from app.services.tsd_realtime import _DOC_CACHE, _get_or_create_session, _snapshot_session

    alice = realtime_tenant["alice"]
    org_id = realtime_tenant["org"]

    sig = SignatureProfile(
        name="Alice Dir", signature_type="drawn",
        signature_data='<svg viewBox="0 0 12 4"><path d="M0 2L12 2"/></svg>',
        user_id=alice.id,
    )
    db.session.add(sig)
    db.session.flush()

    pt0 = tsd_format.pack_content(html="<p>Initial text</p>")
    ct0 = tsd_format.encrypt_content_envelope(pt0, organization_id=org_id)
    doc = TSDocument(
        organization_id=org_id,
        created_by_id=alice.id,
        title="crdt-marks-preserve", ciphertext=ct0,
        ciphertext_sha256=tsd_format.sha256_hex(ct0),
        plaintext_bytes=len(pt0),
    )
    db.session.add(doc)
    db.session.flush()

    usage = SignatureUsageLog(
        organization_id=org_id,
        signature_profile_id=sig.id,
        owner_user_id=alice.id,
        requester_user_id=alice.id,
        document_id=doc.id,
        document_title=doc.title,
        otp_code_hash=SignatureUsageLog.hash_otp("112233"),
        otp_last2="33",
        otp_expires_at=datetime.utcnow() + timedelta(minutes=5),
        status="applied",
        approved_at=datetime.utcnow(),
        applied_at=datetime.utcnow(),
    )
    db.session.add(usage)
    db.session.flush()

    att = issue_signature_attestation(
        organization_id=org_id, document_id=doc.id, signature=sig, usage_log=usage,
    )
    graphic = tsd_format.sanitize_html(sig.signature_data)
    stored_html = (
        '<p>Initial text</p>'
        '<div class="tsd-persisted-marks" data-tsd-marks="1">'
        '<span class="tsd-stamp-mark" data-tsd-stamp-receipt="77" data-tsd-stamp-nonce="xyz">'
        '<svg viewBox="0 0 10 10"><circle cx="5" cy="5" r="4"></circle></svg></span>'
        f'<div class="tsd-sig-block" data-tsd-sig-id="{sig.id}" '
        f'data-tsd-sig-usage="{usage.id}" '
        f'data-tsd-sig-digest="{att["signature_digest"]}" '
        f'data-tsd-sig-attestation="{att["signature_attestation"]}">{graphic}</div>'
        '</div>'
    )
    pt1 = tsd_format.pack_content(html=stored_html)
    ct1 = tsd_format.encrypt_content_envelope(pt1, organization_id=org_id)
    doc.ciphertext = ct1
    doc.ciphertext_sha256 = tsd_format.sha256_hex(ct1)
    doc.plaintext_bytes = len(pt1)
    db.session.commit()

    sess = _get_or_create_session(doc.id)
    try:
        # Simulate ProseMirror CRDT fragment containing ONLY the edited text (no marks)
        sess._initial_html = "<p>Initial text</p><p>Edited via CRDT</p>"
        sess.dirty = True
        assert _snapshot_session(sess, force=True) is True

        db.session.refresh(doc)
        decrypted = tsd_format.decrypt_content_envelope(doc.ciphertext, organization_id=org_id)
        html_after = decrypted["html"]
        assert "Edited via CRDT" in html_after
        assert 'data-tsd-stamp-receipt="77"' in html_after
        assert f'data-tsd-sig-attestation="{att["signature_attestation"]}"' in html_after
    finally:
        _DOC_CACHE.pop(doc.id, None)


def test_crdt_snapshot_rejects_forged_signature_markup(pg_app, realtime_tenant):
    """CRDT snapshots must refuse to persist forged/unattested signature markers."""
    from app.models.tsd_document import TSDocument
    from app.services import tsd_format
    from app.services.tsd_realtime import _DOC_CACHE, _get_or_create_session, _snapshot_session

    org_id = realtime_tenant["org"]
    pt = tsd_format.pack_content(html="<p>Clean</p>")
    ct = tsd_format.encrypt_content_envelope(pt, organization_id=org_id)
    doc = TSDocument(
        organization_id=org_id,
        created_by_id=realtime_tenant["alice"].id,
        title="crdt-forged-sig", ciphertext=ct,
        ciphertext_sha256=tsd_format.sha256_hex(ct),
        plaintext_bytes=len(pt),
    )
    db.session.add(doc)
    db.session.commit()
    orig_version = doc.version

    sess = _get_or_create_session(doc.id)
    try:
        sess._initial_html = (
            '<p>Clean</p><div class="tsd-sig-block" data-tsd-sig-id="1" '
            'data-tsd-sig-usage="1" data-tsd-sig-digest="' + ("0" * 64) + '" '
            'data-tsd-sig-attestation="' + ("f" * 64) + '">Fake</div>'
        )
        sess.dirty = True
        assert _snapshot_session(sess, force=True) is False
        db.session.refresh(doc)
        assert doc.version == orig_version
    finally:
        _DOC_CACHE.pop(doc.id, None)
