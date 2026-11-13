"""Anonymous, upload-only verification of an independently supplied PDF.

This endpoint never looks up a document, tenant, user or receipt. Disabled by
default until ingress rate limits, memory limits and isolated PDF parsing are
configured. Certificate trust and exact issuer fingerprint are mandatory.
"""
import hashlib
import re

from flask import Blueprint, current_app, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

from app.services.platform_pdf_seal import (
    inspect_signed_pdf, PdfFinalizationError, MAX_PDF_BYTES,
)

public_pdf_verify_api = Blueprint(
    "public_pdf_verify_api", __name__, url_prefix="/api/public-verification"
)


def _response(outcome, status=200, **values):
    body = {
        "status": outcome,
        "assurance": "platform_certificate_seal_only",
        "not_individual_signatures": True,
        **values,
    }
    resp = jsonify(body)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp, status


@public_pdf_verify_api.route("/pdf", methods=["POST"])
def verify_uploaded_pdf():
    """Verify bytes supplied by caller, without touching private storage."""
    if not current_app.config.get("PUBLIC_PDF_VERIFICATION_ENABLED", False):
        return _response("unavailable", 503)

    expected_cert = current_app.config.get("PUBLIC_PDF_VERIFICATION_CERT_SHA256")
    if not isinstance(expected_cert, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_cert):
        return _response("unavailable", 503)

    # An explicit evidence digest comes from the document holder's exported
    # review-evidence package. No record ID, URL, or tenant lookup is accepted.
    if set(request.form) != {"evidence_sha256"}:
        return _response("invalid_request", 400)
    evidence_digest = request.form.get("evidence_sha256")
    if not isinstance(evidence_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", evidence_digest):
        return _response("invalid_request", 400)
    if set(request.files) != {"pdf"}:
        return _response("invalid_request", 400)
    file = request.files.get("pdf")
    if file is None or file.filename is None or not file.filename.lower().endswith(".pdf"):
        return _response("invalid_request", 400)
    # Avoid trusting MIME type, Content-Length or a caller-provided file hash.
    # Read one byte past the limit to reject oversized bodies without
    # streaming unbounded data into the verifier.
    try:
        data = file.stream.read(MAX_PDF_BYTES + 1)
    except (OSError, RequestEntityTooLarge):
        return _response("invalid_request", 400)
    if not data or len(data) > MAX_PDF_BYTES or not data.startswith(b"%PDF-"):
        return _response("invalid_request", 400)

    document_digest = hashlib.sha256(data).hexdigest()
    try:
        result = inspect_signed_pdf(
            data, current_app.config,
            expected_evidence_sha256=evidence_digest,
            expected_certificate_sha256=expected_cert,
        )
    except PdfFinalizationError:
        # Do not expose whether a tenant, key, certificate or artifact exists.
        return _response(
            "invalid", document_sha256=document_digest,
            signature_valid=False, intact=False, trusted=False,
        )
    return _response(
        "valid" if result["overall_valid"] else "invalid",
        document_sha256=document_digest,
        signature_valid=bool(result["signature_valid"]),
        intact=bool(result["intact"]),
        trusted=bool(result["trusted"]),
        certificate_sha256=result["certificate_sha256"],
        evidence_sha256=evidence_digest,
    )
