"""Small regression checks for envelope ordering and public route contract.

These do not replace PostgreSQL integration tests of locks and migration.
"""
import pytest
from app.blueprints.documents.api.envelope_api import valid_signing_order, envelope_api


@pytest.mark.parametrize("orders", [
    [1], [1, 2, 3], [3, 1, 2],
])
def test_valid_signing_order(orders):
    assert valid_signing_order(orders)


@pytest.mark.parametrize("orders", [
    [], [2], [1, 3], [1, 1], [0, 1], [True], ["1"], [1, 2, 2],
])
def test_invalid_signing_order(orders):
    assert not valid_signing_order(orders)


def test_envelope_api_is_preparation_only():
    methods = {
        rule.rule: rule.methods for rule in envelope_api.deferred_functions
    } if False else None
    # Explicitly guard against introducing a signing action in this module.
    import inspect
    from app.blueprints.documents.api import envelope_api as module
    source = inspect.getsource(module)
    assert '@envelope_api.route("/<int:envelope_id>/sign"' not in source
    assert "document_sha256" in source
