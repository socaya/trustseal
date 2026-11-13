"""Canonical stamp lineage and authorization API surface regressions."""
from flask import Flask
from app.blueprints.estamp.stamped_pdf_api import stamped_pdf_api
from app.services.stamp_pdf_provenance import (
    build_stamp_provenance, provenance_sha256,
)


def _provenance(**updates):
    parameters = {
        "source_pdf_sha256": "a" * 64,
        "unsigned_pdf_sha256": "b" * 64,
        "signed_review_sha256": "c" * 64,
        "stamp_receipt_sha256": "d" * 64,
        "stamp_attestation_id": 20,
        "stamp_code": "VW-004",
        "page_number": 1,
        "x_pt": 350,
        "y_pt": 60,
    }
    parameters.update(updates)
    return build_stamp_provenance(**parameters)


def test_provenance_binds_original_stamp_and_exact_position():
    first = provenance_sha256(_provenance())
    assert len(first) == 64
    assert first == provenance_sha256(_provenance())
    assert first != provenance_sha256(_provenance(x_pt=351))
    assert first != provenance_sha256(_provenance(y_pt=61))
    assert first != provenance_sha256(_provenance(page_number=2))
    assert first != provenance_sha256(_provenance(stamp_attestation_id=21))
    assert first != provenance_sha256(_provenance(source_pdf_sha256="f" * 64))
    assert first != provenance_sha256(_provenance(stamp_receipt_sha256="e" * 64))


def test_invalid_digest_or_placement_rejected():
    from pytest import raises
    with raises(ValueError):
        _provenance(source_pdf_sha256="not-sha256")
    with raises(ValueError):
        _provenance(page_number=0)
    with raises(ValueError):
        _provenance(x_pt=-1)
    with raises(ValueError):
        _provenance(stamp_attestation_id=True)


def test_stamped_pdf_api_requires_authenticated_read_only_routes():
    app = Flask(__name__)
    app.register_blueprint(stamped_pdf_api)
    routes = {rule.rule: rule.methods for rule in app.url_map.iter_rules()}
    prefix = "/api/stamped-pdfs/<int:artifact_id>"
    assert "GET" in routes[prefix + "/verify"]
    assert "GET" in routes[prefix + "/download"]
    assert all("POST" not in methods for route, methods in routes.items()
               if route.startswith("/api/stamped-pdfs"))
