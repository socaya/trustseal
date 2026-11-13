"""Canonical draft-text snapshot hashing, independent of JSON key order."""
import hashlib
import json


def canonical_snapshot_bytes(document_id, revision, content):
    if type(document_id) is not int or document_id <= 0:
        raise ValueError("Invalid document identifier")
    if type(revision) is not int or revision < 1:
        raise ValueError("Invalid document revision")
    if not isinstance(content, str):
        raise ValueError("Document content must be text")
    return json.dumps(
        {"schema": 1, "document_id": document_id,
         "revision": revision, "content": content},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def snapshot_digest(document_id, revision, content):
    return hashlib.sha256(
        canonical_snapshot_bytes(document_id, revision, content)
    ).hexdigest()
