"""Canonical evidence digest regression cases."""
import pytest
from app.services.platform_review_evidence import canonical_evidence_bundle, evidence_digest


def _receipt(order, identifier):
    return {
        "participant_id": identifier,
        "signing_order": order,
        "review_decision_id": 100 + identifier,
        "payload": {"document_sha256": "a" * 64, "participant_id": identifier},
        "algorithm": "Ed25519",
        "key_id": "ed25519-sha256:" + "f" * 64,
        "signature": "dGVzdA==",
    }


def test_ordered_receipts_are_deterministic():
    items = [_receipt(1, 11), _receipt(2, 22)]
    first = canonical_evidence_bundle(7, items)
    second = canonical_evidence_bundle(7, list(items))
    assert evidence_digest(first) == evidence_digest(second)
    assert len(evidence_digest(first)) == 64


def test_modified_receipt_changes_signed_pdf_evidence_digest():
    original = canonical_evidence_bundle(7, [_receipt(1, 11)])
    modified = canonical_evidence_bundle(7, [_receipt(1, 11)])
    modified["receipts"][0]["signature"] = "changed"
    assert evidence_digest(original) != evidence_digest(modified)


@pytest.mark.parametrize("receipts", [
    [], [_receipt(2, 11)],
    [_receipt(1, 11), _receipt(2, 11)],
    [_receipt(1, 11), _receipt(3, 22)],
])
def test_invalid_order_or_duplicates_rejected(receipts):
    with pytest.raises(ValueError):
        canonical_evidence_bundle(7, receipts)
