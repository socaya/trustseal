"""Anonymous, upload-only verification of an independently supplied PDF.

Two levels of verification:

* **Shallow.** Legacy path (``PUBLIC_PDF_VERIFICATION_ENABLED=true``):
  verify the embedded CMS and compare the signing certificate SHA-256
  against the pinned fingerprint. No DB lookup. Preserved for
  backwards-compatibility with callers that only care about seal
  provenance.

* **Deep.** New path (``PUBLIC_VERIFICATION_DEEP_ENABLED=true``):
  look up the :class:`EvidenceRetention` by the uploaded document's
  SHA-256, load the most recent dossier, and run
  :func:`validation_dossier.verify_dossier`. Returns the dossier's
  timestamp, revocation observations, chain, and the missing-
  requirements list so callers can see exactly what assurance they
  are getting (closes gap G13).

When both are enabled deep wins. The two paths return the same
response envelope with distinct verdict codes so downstream clients
can switch on ``status``.
"""
import hashlib
import re

from flask import Blueprint, current_app, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

from app.services.platform_pdf_seal import (
    MAX_PDF_BYTES,
    PdfFinalizationError,
    inspect_signed_pdf,
)
from app.services.public_verification import SHA256_RE, deep_verify

public_pdf_verify_api = Blueprint(
    "public_pdf_verify_api", __name__, url_prefix="/api/public-verification"
)


def _response(outcome, status=200, *, assurance="platform_certificate_seal_only", **values):
    body = {
        "status": outcome,
        "assurance": assurance,
        "not_individual_signatures": True,
        **values,
    }
    resp = jsonify(body)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp, status


def _read_upload():
    """Return the uploaded PDF bytes or a response-tuple to short-circuit."""
    if set(request.files) != {"pdf"}:
        return None, _response("invalid_request", 400)
    file = request.files.get("pdf")
    if (
        file is None
        or file.filename is None
        or not file.filename.lower().endswith(".pdf")
    ):
        return None, _response("invalid_request", 400)
    try:
        data = file.stream.read(MAX_PDF_BYTES + 1)
    except (OSError, RequestEntityTooLarge):
        return None, _response("invalid_request", 400)
    if not data or len(data) > MAX_PDF_BYTES or not data.startswith(b"%PDF-"):
        return None, _response("invalid_request", 400)
    return data, None


@public_pdf_verify_api.route("/pdf", methods=["POST"])
def verify_uploaded_pdf():
    """Verify bytes supplied by caller.

    Shallow path: requires only ``evidence_sha256`` in the form.
    Deep path: requires either ``artifact_sha256`` (preferred) or
    ``evidence_sha256``. The deep lookup uses the computed document
    SHA-256 anyway, so ``artifact_sha256`` is treated as a client
    assertion rather than an input.
    """
    deep_enabled = bool(current_app.config.get("PUBLIC_VERIFICATION_DEEP_ENABLED", False))
    shallow_enabled = bool(
        current_app.config.get("PUBLIC_PDF_VERIFICATION_ENABLED", False)
    )
    if not (deep_enabled or shallow_enabled):
        return _response("unavailable", 503)

    data, early = _read_upload()
    if early is not None:
        return early

    # Deep path — authoritative when enabled.
    if deep_enabled:
        return _render_deep(data)

    # Shallow fallback — the pinned-fingerprint path.
    return _render_shallow(data)


def _render_deep(data: bytes):
    document_sha256 = hashlib.sha256(data).hexdigest()
    # Client-asserted artifact_sha256 is optional but, when supplied,
    # must match the computed digest so a tampered body is caught
    # before any DB work.
    asserted = request.form.get("artifact_sha256")
    if asserted is not None:
        if not isinstance(asserted, str) or not SHA256_RE.match(asserted):
            return _response(
                "invalid_request",
                400,
                assurance="deep_dossier_verification",
            )
        if asserted != document_sha256:
            return _response(
                "mismatch",
                200,
                assurance="deep_dossier_verification",
                document_sha256=document_sha256,
                asserted_sha256=asserted,
                reason="document_sha256_differs",
            )

    try:
        result = deep_verify(document_sha256, data, current_app.config)
    except ValueError:
        return _response(
            "invalid_request",
            400,
            assurance="deep_dossier_verification",
        )

    payload: dict = {
        "status": result.verdict,
        "assurance": "deep_dossier_verification",
        "not_individual_signatures": True,
        "document_sha256": result.document_sha256,
    }
    if result.reason:
        payload["reason"] = result.reason
    if result.retention_id is not None:
        payload["retention_id"] = result.retention_id
    if result.timestamp is not None:
        payload["timestamp"] = result.timestamp
    if result.revocation_observations is not None:
        payload["revocation_observations"] = result.revocation_observations
    if result.missing_requirements is not None:
        payload["missing_requirements"] = result.missing_requirements
    if result.certificate_chain is not None:
        payload["certificate_chain"] = {
            "leaf_sha256": result.certificate_chain.get("leaf_sha256"),
            "intermediate_sha256s": result.certificate_chain.get(
                "intermediate_sha256s", []
            ),
        }
    if result.platform_signer_chain is not None:
        payload["platform_signer_chain"] = {
            "signer_certificate_sha256": result.platform_signer_chain.get(
                "signer_certificate_sha256"
            ),
            "has_full_chain_evidence": bool(
                result.platform_signer_chain.get("crl_inventory")
            ),
        }
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response, 200


def _render_shallow(data: bytes):
    expected_cert = current_app.config.get("PUBLIC_PDF_VERIFICATION_CERT_SHA256")
    if not isinstance(expected_cert, str) or not re.fullmatch(
        r"[0-9a-f]{64}", expected_cert
    ):
        return _response("unavailable", 503)

    if set(request.form) - {"evidence_sha256", "artifact_sha256"} or (
        "evidence_sha256" not in request.form
    ):
        return _response("invalid_request", 400)
    evidence_digest = request.form.get("evidence_sha256")
    if not isinstance(evidence_digest, str) or not re.fullmatch(
        r"[0-9a-f]{64}", evidence_digest
    ):
        return _response("invalid_request", 400)
    document_digest = hashlib.sha256(data).hexdigest()
    try:
        result = inspect_signed_pdf(
            data,
            current_app.config,
            expected_evidence_sha256=evidence_digest,
            expected_certificate_sha256=expected_cert,
        )
    except PdfFinalizationError:
        return _response(
            "invalid",
            document_sha256=document_digest,
            signature_valid=False,
            intact=False,
            trusted=False,
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
