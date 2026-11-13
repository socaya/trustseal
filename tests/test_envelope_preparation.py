"""Envelope order and public API-surface regressions.

These are isolated unit cases; they do not replace PostgreSQL integration tests.
"""
import pytest
from flask import Flask

from app.blueprints.documents.api.envelope_api import valid_signing_order, envelope_api


@pytest.mark.parametrize("orders", [[1], [1, 2, 3], [3, 1, 2]])
def test_valid_signing_order(orders):
    assert valid_signing_order(orders)


@pytest.mark.parametrize("orders", [
    [], [2], [1, 3], [1, 1], [0, 1], [True], ["1"], [1, 2, 2],
])
def test_invalid_signing_order(orders):
    assert not valid_signing_order(orders)


def test_envelope_api_has_no_sign_endpoint():
    app = Flask(__name__)
    app.register_blueprint(envelope_api)
    routes = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/api/envelopes/<int:envelope_id>/prepare" in routes
    assert "/api/envelopes/<int:envelope_id>/cancel" in routes
    assert not any(route.endswith("/sign") or route.endswith("/complete") for route in routes)
