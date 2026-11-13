"""Draft text digest regression tests.

A digest is evidence of content consistency within this application only,
not proof of a signer, timestamp authority, or certificate.
"""
import hashlib
import json

import pytest

from app.services.documents.snapshots import (
    canonical_snapshot_bytes, snapshot_digest,
)


def test_canonical_bytes_are_deterministic():
    encoded = canonical_snapshot_bytes(23, 4, "Uganda / Kampala")
    expected = json.dumps(
        {"schema": 1, "document_id": 23, "revision": 4,
         "content": "Uganda / Kampala"},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    assert encoded == expected
    assert snapshot_digest(23, 4, "Uganda / Kampala") == hashlib.sha256(expected).hexdigest()


def test_content_and_revision_changes_alter_digest():
    baseline = snapshot_digest(23, 4, "Original")
    assert baseline != snapshot_digest(23, 4, "Changed")
    assert baseline != snapshot_digest(23, 5, "Original")
    assert baseline != snapshot_digest(24, 4, "Original")


@pytest.mark.parametrize("document_id,revision,content", [
    (0, 1, "x"), (1, 0, "x"), ("1", 1, "x"), (1, 1, None),
    (True, 1, "x"), (1, True, "x"),
])
def test_invalid_inputs_fail_closed(document_id, revision, content):
    with pytest.raises(ValueError):
        snapshot_digest(document_id, revision, content)


def test_unicode_remains_stable():
    assert snapshot_digest(1, 2, "Lango — Acholi") == snapshot_digest(
        1, 2, "Lango — Acholi"
    )
