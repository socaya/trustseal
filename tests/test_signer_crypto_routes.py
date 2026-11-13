"""Check signer cryptographic API surface; no private key upload route exists."""
from flask import Flask
from app.blueprints.documents.api.signer_crypto_api import signer_crypto_api


def test_signer_crypto_routes_are_explicit_and_bound():
    app = Flask(__name__)
    app.register_blueprint(signer_crypto_api)
    routes = {rule.rule: rule.methods for rule in app.url_map.iter_rules()}
    prefix = "/api/signer-crypto"
    assert "POST" in routes[prefix + "/keys/challenge"]
    assert "POST" in routes[prefix + "/keys/confirm"]
    assert "GET" in routes[prefix + "/keys"]
    assert "POST" in routes[prefix + "/keys/<int:key_id>/revoke"]
    assert "POST" in routes[prefix + "/envelopes/<int:envelope_id>/challenge"]
    assert "POST" in routes[prefix + "/envelopes/<int:envelope_id>/endorse"]
    assert "GET" in routes[prefix + "/envelopes/<int:envelope_id>/endorsement"]
    assert not any("private-key" in p or "key-upload" in p for p in routes)
