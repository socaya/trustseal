"""Canonical provenance for visible stamped PDF derivatives.

The original signed PDF is retained unchanged. The derivative embeds one
new CMS platform signature over the visible imprint and this evidence digest.
"""
import hashlib
import json
import re


def build_stamp_provenance(*, source_pdf_sha256, unsigned_pdf_sha256,
                           signed_review_sha256, stamp_receipt_sha256,
                           stamp_attestation_id, stamp_code, page_number,
                           x_pt, y_pt):
    values = (source_pdf_sha256, unsigned_pdf_sha256,
              signed_review_sha256, stamp_receipt_sha256)
    if any(not isinstance(v, str) or not re.fullmatch("[0-9a-f]{64}", v) for v in values):
        raise ValueError("Invalid source or attestation digest")
    if (type(stamp_attestation_id) is not int or stamp_attestation_id < 1
            or not isinstance(stamp_code, str) or not 3 <= len(stamp_code) <= 32
            or type(page_number) is not int or page_number < 1
            or type(x_pt) is not int or type(y_pt) is not int
            or x_pt < 0 or y_pt < 0):
        raise ValueError("Invalid stamp provenance placement")
    return {
        "schema": "trustseal.visible-stamp-provenance.v1",
        "source_finalized_pdf_sha256": source_pdf_sha256,
        "source_unsigned_pdf_sha256": unsigned_pdf_sha256,
        "source_review_evidence_sha256": signed_review_sha256,
        "stamp_attestation_sha256": stamp_receipt_sha256,
        "stamp_attestation_id": stamp_attestation_id,
        "stamp_code": stamp_code,
        "placement": {"page_number": page_number, "x_pt": x_pt, "y_pt": y_pt},
    }


def provenance_sha256(provenance):
    canonical = json.dumps(
        provenance, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
