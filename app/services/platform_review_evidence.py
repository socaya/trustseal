"""Canonical, bounded evidence bundle for a platform-sealed PDF.

Receipt list must be in participant signing order and independently validated.
An evidence bundle is not a trusted timestamp or signer PKI certificate.
"""
import hashlib
import json


def canonical_evidence_bundle(envelope_id, receipt_items):
    if type(envelope_id) is not int or envelope_id < 1:
        raise ValueError("Invalid envelope ID")
    if not isinstance(receipt_items, list) or not 0 < len(receipt_items) <= 100:
        raise ValueError("Evidence requires 1 to 100 ordered receipts")
    seen = set()
    previous = 0
    for item in receipt_items:
        if not isinstance(item, dict):
            raise ValueError("Invalid receipt item")
        participant_id = item.get("participant_id")
        if type(participant_id) is not int or participant_id in seen:
            raise ValueError("Duplicate or invalid receipt participant")
        seen.add(participant_id)
        position = item.get("signing_order")
        if type(position) is not int or position != previous + 1:
            raise ValueError("Receipt order is not contiguous")
        previous = position
    return {"schema": 1, "envelope_id": envelope_id, "receipts": receipt_items}


def evidence_digest(bundle):
    contents = json.dumps(
        bundle, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(contents).hexdigest()
