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
