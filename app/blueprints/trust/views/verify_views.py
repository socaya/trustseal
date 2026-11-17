"""Public verification UI.

Two pages:

* ``GET /verify`` — upload-only verification form. The client POSTs a
  PDF and an evidence digest; the view delegates to the same logic as
  :mod:`app.blueprints.documents.api.public_pdf_verify_api` and renders
  a server-side result.
* ``POST /verify/pdf`` — form handler. Returns the same template with
  the verdict populated.

The page intentionally contains no JavaScript framework and no PDF
viewer embed. Document bytes are compared server-side; the browser
never receives the uploaded file back. The resulting page is safe to
render for any visitor.

A simple in-memory rate limiter prevents accidental abuse by a single
IP. Production should front this with a dedicated edge rate-limiter;
the in-process limit is defence in depth.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from flask import (
    Blueprint,
    current_app,
    render_template,
    request,
)
from flask_login import current_user
from werkzeug.exceptions import RequestEntityTooLarge


def _verify_template() -> str:
    """Pick the authenticated app shell when the caller is signed in.

    Verification is a public service, but a signed-in operator who
    clicks "Verification" from the sidebar shouldn't be dumped out
    of their workspace into the stripped public shell.
    """
    try:
        if current_user.is_authenticated:
            return "trust/verify_app.html"
    except Exception:
        pass
    return "trust/verify.html"

from app.services.platform_pdf_seal import (
    MAX_PDF_BYTES,
    PdfFinalizationError,
    inspect_signed_pdf,
)
from app.services.rate_limiting import RateLimitError, consume

verify_views = Blueprint(
    "verify_views",
    __name__,
    url_prefix="/verify",
    template_folder="../../../templates",
)

_CERT_HEX = re.compile(r"[0-9a-f]{64}")
_WINDOW_SECONDS = 60
_MAX_REQUESTS_PER_WINDOW = 10


def _client_identifier() -> str:
    """Return a stable identifier for rate-limiting.

    We prefer ``X-Forwarded-For`` when deployed behind a trusted proxy;
    otherwise ``request.remote_addr``. Either way we hash the value so
    the raw IP never appears in logs.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    raw = forwarded.split(",")[0].strip() if forwarded else (request.remote_addr or "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _rate_limited() -> bool:
    identity = _client_identifier()
    try:
        decision = consume(
            bucket_key=f"verify:{identity}",
            max_hits=_MAX_REQUESTS_PER_WINDOW,
            window_seconds=_WINDOW_SECONDS,
        )
    except RateLimitError:
        return False
    return not decision.allowed


def _verdict_from(result: dict[str, Any]) -> tuple[str, str]:
    """Map the raw ``inspect_signed_pdf`` result to a UI verdict."""
    if result.get("overall_valid"):
        return "valid", "Document is intact and sealed by the platform certificate."
    if not result.get("intact"):
        return "mismatch", "The uploaded bytes do not match the sealed document."
    if not result.get("trusted"):
        return "untrusted", "The signature does not match the pinned platform certificate."
    return "invalid", "Verification failed. The document may have been altered."


@verify_views.route("", methods=["GET"])
def verify_form():
    """Render the empty upload form."""
    enabled = bool(current_app.config.get("PUBLIC_PDF_VERIFICATION_ENABLED", False))
    return render_template(
        _verify_template(),
        enabled=enabled,
        verdict=None,
        verdict_detail=None,
        document_sha256=None,
        certificate_sha256=None,
        evidence_sha256=None,
        error=None,
    )


@verify_views.route("/pdf", methods=["POST"])
def verify_pdf():
    """Handle a POST from the verification form and render the verdict."""
    if _rate_limited():
        return (
            render_template(
                _verify_template(),
                enabled=True,
                verdict=None,
                verdict_detail=None,
                document_sha256=None,
                certificate_sha256=None,
                evidence_sha256=None,
                error="Too many verification attempts. Please wait a moment and retry.",
            ),
            429,
        )
    if not current_app.config.get("PUBLIC_PDF_VERIFICATION_ENABLED", False):
        return (
            render_template(
                _verify_template(),
                enabled=False,
                verdict=None,
                verdict_detail=None,
                document_sha256=None,
                certificate_sha256=None,
                evidence_sha256=None,
                error="Public verification is not enabled on this deployment.",
            ),
            503,
        )

    expected_cert = current_app.config.get("PUBLIC_PDF_VERIFICATION_CERT_SHA256")
    if not isinstance(expected_cert, str) or not _CERT_HEX.fullmatch(expected_cert):
        return (
            render_template(
                _verify_template(),
                enabled=True,
                verdict=None,
                verdict_detail=None,
                document_sha256=None,
                certificate_sha256=None,
                evidence_sha256=None,
                error="Verification configuration is incomplete.",
            ),
            503,
        )

    evidence_digest = (request.form.get("evidence_sha256") or "").strip().lower()
    if not _CERT_HEX.fullmatch(evidence_digest):
        return _render_bad_request("Provide the 64-character evidence digest.")

    pdf_file = request.files.get("pdf")
    if pdf_file is None or not (pdf_file.filename or "").lower().endswith(".pdf"):
        return _render_bad_request("Attach the PDF you would like to verify.")

    try:
        data = pdf_file.stream.read(MAX_PDF_BYTES + 1)
    except (OSError, RequestEntityTooLarge):
        return _render_bad_request("The uploaded file could not be read.")
    if not data:
        return _render_bad_request("The uploaded file is empty.")
    if len(data) > MAX_PDF_BYTES:
        return _render_bad_request("The uploaded file exceeds the size limit.")
    if not data.startswith(b"%PDF-"):
        return _render_bad_request("The uploaded file is not a PDF.")

    document_digest = hashlib.sha256(data).hexdigest()
    try:
        result = inspect_signed_pdf(
            data,
            current_app.config,
            expected_evidence_sha256=evidence_digest,
            expected_certificate_sha256=expected_cert,
        )
    except PdfFinalizationError:
        return (
            render_template(
                _verify_template(),
                enabled=True,
                verdict="invalid",
                verdict_detail="Verification failed. The document may have been altered or sealed by a different platform.",
                document_sha256=document_digest,
                certificate_sha256=None,
                evidence_sha256=evidence_digest,
                error=None,
            ),
            200,
        )

    verdict, detail = _verdict_from(result)
    return (
        render_template(
            _verify_template(),
            enabled=True,
            verdict=verdict,
            verdict_detail=detail,
            document_sha256=document_digest,
            certificate_sha256=result.get("certificate_sha256"),
            evidence_sha256=evidence_digest,
            error=None,
        ),
        200,
    )


def _render_bad_request(message: str):
    return (
        render_template(
            _verify_template(),
            enabled=True,
            verdict=None,
            verdict_detail=None,
            document_sha256=None,
            certificate_sha256=None,
            evidence_sha256=None,
            error=message,
        ),
        400,
    )
