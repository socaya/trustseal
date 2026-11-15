"""Structured logging, request IDs, and sensitive-field redaction.

This module replaces ad-hoc ``logging.Formatter`` wiring in
``app/__init__.py``. Call :func:`configure_observability` from the Flask
application factory. After configuration:

* ``current_app.logger`` writes structured events.
* A module-level :data:`log` provides a structlog ``BoundLogger`` usable
  from services and workers.
* Every request carries a correlation id in ``g.request_id`` and in the
  ``X-Request-ID`` response header; the id is bound to the request-scoped
  logger context automatically.
* A redaction processor strips known sensitive keys from event dicts, so
  tokens, document bytes, signatures, and personal data never reach stdout.

Design notes:

* We avoid adding a new log transport. ``structlog`` renders to JSON on a
  stdlib ``StreamHandler`` so the existing stdout sink (systemd, container
  runtime, journald) keeps working.
* The redaction set is narrow and explicit. Expand it in review, not by
  guessing. See ``REDACT_KEYS``.
"""
from __future__ import annotations

import logging
import os
import sys
import uuid
from typing import Any, Mapping

import structlog
from flask import Flask, g, has_request_context, request

REDACT_KEYS: frozenset[str] = frozenset(
    {
        # Credentials and token material.
        "password",
        "password_hash",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "idempotency_key",
        "api_key",
        "authorization",
        "jwt",
        # Cryptographic key material and raw bytes.
        "private_key",
        "pem",
        "pkcs12",
        "pkcs12_password",
        "signature",
        "signature_value",
        "cms",
        "content",  # document content
        "document_content",
        "body_bytes",
        # Personal data.
        "email",
        "phone",
        "ip_address",
        "user_agent",
    }
)

REDACTED = "***"


def _redact(value: Any, depth: int = 0) -> Any:
    """Recursively replace sensitive fields and truncate oversized bytes.

    ``depth`` guards against pathological nested structures the logger
    occasionally receives (e.g. SQLAlchemy relationship payloads). Stops
    recursion at depth 6.
    """
    if depth > 6:
        return REDACTED
    if isinstance(value, Mapping):
        return {
            k: (REDACTED if isinstance(k, str) and k.lower() in REDACT_KEYS else _redact(v, depth + 1))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return type(value)(_redact(v, depth + 1) for v in value)
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    if isinstance(value, str) and len(value) > 2048:
        return value[:2048] + "…"
    return value


def _redact_processor(_logger, _method, event_dict: dict[str, Any]) -> dict[str, Any]:
    return {
        k: (REDACTED if isinstance(k, str) and k.lower() in REDACT_KEYS else _redact(v))
        for k, v in event_dict.items()
    }


def _bind_request_context(_logger, _method, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Inject request-scoped context automatically.

    When called outside a request context, do nothing. This keeps the
    worker-side loggers from blowing up when they emit events during a
    background job.
    """
    if has_request_context():
        request_id = getattr(g, "request_id", None)
        if request_id:
            event_dict.setdefault("request_id", request_id)
        event_dict.setdefault("method", request.method)
        event_dict.setdefault("path", request.path)
    return event_dict


def _resolve_level(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return getattr(logging, value.upper(), logging.INFO)
    return logging.INFO


log = structlog.get_logger("trustseal")


def configure_observability(app: Flask) -> None:
    """Install structured logging and request-ID middleware on ``app``.

    Idempotent — repeated calls do not stack handlers. Safe to call from
    the application factory during tests and in production.
    """
    level = _resolve_level(app.config.get("LOGGING_LEVEL", "INFO"))
    pretty = str(app.config.get("FLASK_ENV", "")).lower() in {"development", "testing"} and os.getenv(
        "TRUSTSEAL_JSON_LOGS", "0"
    ) != "1"

    renderer = (
        structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
        if pretty
        else structlog.processors.JSONRenderer()
    )

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _bind_request_context,
        _redact_processor,
        renderer,
    ]
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    root = logging.getLogger()
    # Replace handlers rather than stack them, so repeated factory calls
    # do not emit duplicate lines in tests.
    for handler in list(root.handlers):
        root.removeHandler(handler)
    stream = logging.StreamHandler()
    stream.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(stream)
    root.setLevel(level)

    # Replace the Flask app logger handlers in the same way.
    for handler in list(app.logger.handlers):
        app.logger.removeHandler(handler)
    app.logger.propagate = True
    app.logger.setLevel(level)

    @app.before_request
    def _assign_request_id() -> None:  # pragma: no cover - trivial
        incoming = request.headers.get("X-Request-ID", "").strip()
        g.request_id = incoming[:64] if incoming else uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=g.request_id)

    @app.after_request
    def _emit_request_id(response):  # pragma: no cover - trivial
        request_id = getattr(g, "request_id", None)
        if request_id:
            response.headers["X-Request-ID"] = request_id
        return response

    @app.teardown_request
    def _clear_context(_exc=None):  # pragma: no cover - trivial
        structlog.contextvars.clear_contextvars()
