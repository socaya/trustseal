"""Anonymous PDF verification contract and privacy isolation tests."""
from io import BytesIO
from unittest.mock import patch

from flask import Flask
from app.blueprints.documents.api.public_pdf_verify_api import public_pdf_verify_api

SHA = "a" * 64
CERT = "b" * 64


def _app(*, enabled=True, fingerprint=CERT):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        PUBLIC_PDF_VERIFICATION_ENABLED=enabled,
        PUBLIC_PDF_VERIFICATION_CERT_SHA256=fingerprint,
        MAX_CONTENT_LENGTH=17 * 1024 * 1024,
    )
    app.register_blueprint(public_pdf_verify_api)
    return app


def _post(app, digest=SHA, pdf=b"%PDF-1.7\n%%EOF", filename="sealed.pdf"):
    return app.test_client().post(
        "/api/public-verification/pdf",
        data={
            "evidence_sha256": digest,
            "pdf": (BytesIO(pdf), filename, "application/pdf"),
        },
        content_type="multipart/form-data",
    )


def test_public_verification_disabled_by_default():
    app = _app(enabled=False)
    with patch("app.blueprints.documents.api.public_pdf_verify_api.inspect_signed_pdf") as validator:
        response = _post(app)
        assert response.status_code == 503
        assert response.get_json()["status"] == "unavailable"
        validator.assert_not_called()


def test_public_verification_requires_explicit_certificate_fingerprint():
    app = _app(fingerprint=None)
    with patch("app.blueprints.documents.api.public_pdf_verify_api.inspect_signed_pdf") as validator:
        response = _post(app)
        assert response.status_code == 503
        validator.assert_not_called()


def test_public_verification_checks_pdf_and_exact_public_metadata_only():
    app = _app()
    with patch(
        "app.blueprints.documents.api.public_pdf_verify_api.inspect_signed_pdf",
        return_value={
            "overall_valid": True, "signature_valid": True, "intact": True,
            "trusted": True, "certificate_sha256": CERT,
        },
    ) as validator:
        response = _post(app)
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["status"] == "valid"
        assert payload["assurance"] == "platform_certificate_seal_only"
        assert "organization_id" not in payload
        assert "user_id" not in payload
        assert "document_name" not in payload
        assert response.headers["Cache-Control"] == "no-store"
        assert validator.call_args.kwargs["expected_certificate_sha256"] == CERT
        assert validator.call_args.kwargs["expected_evidence_sha256"] == SHA


def test_invalid_document_returns_generic_result_without_database_lookup():
    from app.services.platform_pdf_seal import PdfFinalizationError
    app = _app()
    with patch(
        "app.blueprints.documents.api.public_pdf_verify_api.inspect_signed_pdf",
        side_effect=PdfFinalizationError("internal trust root path /secure/ca.pem"),
    ):
        response = _post(app)
        assert response.status_code == 200
        body = response.get_json()
        assert body["status"] == "invalid"
        assert "ca.pem" not in response.get_data(as_text=True)


def test_bad_input_is_rejected_before_crypto():
    app = _app()
    with patch("app.blueprints.documents.api.public_pdf_verify_api.inspect_signed_pdf") as validator:
        assert _post(app, digest="invalid").status_code == 400
        assert _post(app, pdf=b"not a PDF").status_code == 400
        assert _post(app, filename="not-pdf.txt").status_code == 400
        validator.assert_not_called()


def test_large_document_refused_before_crypto():
    app = _app()
    with patch("app.blueprints.documents.api.public_pdf_verify_api.inspect_signed_pdf") as validator:
        response = _post(app, pdf=b"%PDF-" + b"x" * (16 * 1024 * 1024))
        assert response.status_code in (400, 413)
        validator.assert_not_called()
