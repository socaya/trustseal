"""Signer intent safeguards and digest identity regression tests.

These are local pure/route tests, not a substitute for PostgreSQL and
authentication integration tests.
"""
from types import SimpleNamespace
from flask import Flask

from app.blueprints.documents.api.signer_intent_api import (
    CONSENT_TEXT, CONSENT_VERSION, _decision_digest, signer_intent_api,
)


def test_intent_digest_binds_signer_pdf_envelope_and_choice():
    envelope = SimpleNamespace(id=12, document_sha256="a" * 64)
    participant = SimpleNamespace(id=25)
    baseline = _decision_digest(envelope, participant, 11, "acknowledged")
    assert len(baseline) == 64
    assert baseline == _decision_digest(envelope, participant, 11, "acknowledged")
    assert baseline != _decision_digest(envelope, participant, 11, "declined")
    assert baseline != _decision_digest(envelope, participant, 12, "acknowledged")
    assert baseline != _decision_digest(envelope, SimpleNamespace(id=26), 11, "acknowledged")
    assert baseline != _decision_digest(
        SimpleNamespace(id=12, document_sha256="b" * 64),
        participant, 11, "acknowledged"
    )


def test_consent_version_and_text_do_not_claim_to_sign():
    assert CONSENT_VERSION == "review-intent-v1"
    assert "not a cryptographic" in CONSENT_TEXT
    assert "review" in CONSENT_TEXT


def test_routes_are_review_only():
    app = Flask(__name__)
    app.register_blueprint(signer_intent_api)
    routes = {rule.rule: rule.methods for rule in app.url_map.iter_rules()}
    base = "/api/signer-intent/envelopes/<int:envelope_id>"
    assert "GET" in routes[base]
    assert "GET" in routes[base + "/document"]
    assert "POST" in routes[base + "/challenge"]
    assert "POST" in routes[base + "/decision"]
    assert all(not path.endswith("/sign") for path in routes)
    assert all(not path.endswith("/finalize") for path in routes)
