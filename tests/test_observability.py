"""Structured logging, request-ID, and redaction contract.

Covers:

* X-Request-ID is echoed back on every response.
* X-Request-ID is accepted when provided and otherwise generated.
* ``g.request_id`` is bound to the request logger context.
* Sensitive keys (``password``, ``access_token``, ``signature``, …) are
  replaced with ``***`` in the rendered log output.
* Large byte buffers are summarised, not logged verbatim.
* Repeated factory calls do not stack handlers (would duplicate output).
"""
from __future__ import annotations

import json
import logging
import os

import pytest
import structlog
from flask import g, jsonify

os.environ.setdefault("TRUSTSEAL_JSON_LOGS", "1")


@pytest.fixture
def app(pg_app):
    return pg_app


class TestRequestId:
    def test_generated_when_missing(self, app):
        r = app.test_client().get("/_obs/probe")
        rid = r.headers.get("X-Request-ID")
        assert rid, "response must carry X-Request-ID"
        assert r.get_json()["request_id"] == rid

    def test_echoed_when_supplied(self, app):
        supplied = "abc123-client-correlation"
        r = app.test_client().get("/_obs/probe", headers={"X-Request-ID": supplied})
        assert r.headers.get("X-Request-ID") == supplied
        assert r.get_json()["request_id"] == supplied

    def test_long_incoming_id_truncated(self, app):
        huge = "x" * 500
        r = app.test_client().get("/_obs/probe", headers={"X-Request-ID": huge})
        assert len(r.headers["X-Request-ID"]) <= 64


class TestRedaction:
    def test_sensitive_keys_redacted(self, app, caplog):
        from app.observability import _redact_processor

        event = {
            "event": "test_event",
            "password": "hunter2",
            "access_token": "jwt-secret",
            "signature": "deadbeef",
            "nested": {
                "refresh_token": "nope",
                "ok": "visible",
            },
        }
        out = _redact_processor(None, "info", dict(event))
        assert out["password"] == "***"
        assert out["access_token"] == "***"
        assert out["signature"] == "***"
        assert out["nested"]["refresh_token"] == "***"
        assert out["nested"]["ok"] == "visible"

    def test_bytes_summarised_not_logged(self, app):
        from app.observability import _redact

        result = _redact({"blob": b"\x00" * 10_000})
        assert result == {"blob": "<10000 bytes>"}

    def test_long_strings_truncated(self, app):
        from app.observability import _redact

        result = _redact("x" * 3000)
        assert result.endswith("…")
        assert len(result) == 2049


class TestFactoryIdempotency:
    def test_repeated_configure_does_not_duplicate_handlers(self):
        from app import create_app
        from app.observability import configure_observability

        a1 = create_app()
        configure_observability(a1)
        root_handlers_before = len(logging.getLogger().handlers)
        configure_observability(a1)
        configure_observability(a1)
        assert len(logging.getLogger().handlers) == root_handlers_before


class TestStructlogRendering:
    def test_json_renderer_emits_valid_json(self, app, caplog):
        import logging

        from app.observability import log

        with caplog.at_level(logging.INFO, logger="trustseal"):
            log.info("test_message", key="value", password="secret")
        rendered = [r.getMessage() for r in caplog.records if r.name == "trustseal"]
        parsed = [line for line in rendered if line.startswith("{")]
        assert parsed, "at least one line must be JSON"
        payload = json.loads(parsed[-1])
        assert payload["event"] == "test_message"
        assert payload["key"] == "value"
        assert payload["password"] == "***"
