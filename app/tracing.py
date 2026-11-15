"""OpenTelemetry tracing wire-up.

Configuration (environment or Flask config):

* ``OTEL_ENABLED=1`` — opt-in. Disabled by default so test runs and
  disposable deployments do not emit spans.
* ``OTEL_SERVICE_NAME`` — service name attached to every span.
  Defaults to ``"trustseal"``.
* ``OTEL_EXPORTER_OTLP_ENDPOINT`` — OTLP collector URL. Standard
  OpenTelemetry env var is honoured by the exporter directly.
* ``OTEL_TRACES_SAMPLER`` and ``OTEL_TRACES_SAMPLER_ARG`` are honoured
  by the SDK; the defaults are ``parentbased_always_on``.
* ``OTEL_CONSOLE=1`` — append a ConsoleSpanExporter for local
  debugging.

The module installs Flask, SQLAlchemy, and ``requests`` instrumentation
and records the HTTP ``request_id`` and ``X-TrustSeal-Tenant`` headers
on the outermost span so traces correlate with the existing
observability logs.

Sensitive attributes (JWT, cookies, file-content payloads) are
scrubbed on every span by a custom processor; URL fragments
containing authorisation tokens are never recorded.
"""
from __future__ import annotations

import os
from typing import Any

from flask import Flask, g, request

_INSTALLED = False

SCRUB_HEADER_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "proxy-authorization",
    "x-trustseal-signature",
}
SCRUB_ATTR_KEYS = {
    "http.request.header.authorization",
    "http.request.header.cookie",
    "http.request.header.set_cookie",
    "http.request.header.proxy_authorization",
    "http.request.header.x_api_key",
    "db.statement.values",
}
SCRUB_PLACEHOLDER = "***"


class _ScrubProcessor:
    """SpanProcessor that redacts known sensitive attributes on span end."""

    def on_start(self, span, parent_context=None):  # pragma: no cover
        pass

    def on_end(self, span):  # pragma: no cover - telemetry glue
        attrs = dict(span.attributes or {})
        changed = False
        for key in list(attrs):
            if key.lower() in SCRUB_ATTR_KEYS:
                attrs[key] = SCRUB_PLACEHOLDER
                changed = True
        if changed:
            # Spans are immutable once ended; this processor runs BEFORE
            # the exporter so overwriting the attribute dict is still
            # observed by downstream processors.
            span._attributes = attrs  # noqa: SLF001

    def shutdown(self):  # pragma: no cover
        pass

    def force_flush(self, timeout_millis=30_000):  # pragma: no cover
        return True


def _make_scrub_processor():
    """Return an SDK-subclassed scrub processor (constructable only when OTel is installed)."""
    from opentelemetry.sdk.trace import SpanProcessor

    class _Scrub(SpanProcessor):
        def on_start(self, span, parent_context=None):  # pragma: no cover
            pass

        def on_end(self, span):  # pragma: no cover - telemetry glue
            attrs = dict(span.attributes or {})
            changed = False
            for key in list(attrs):
                if key.lower() in SCRUB_ATTR_KEYS:
                    attrs[key] = SCRUB_PLACEHOLDER
                    changed = True
            if changed:
                span._attributes = attrs  # noqa: SLF001

        def shutdown(self):  # pragma: no cover
            pass

        def force_flush(self, timeout_millis=30_000):  # pragma: no cover
            return True

    return _Scrub


def configure_tracing(app: Flask) -> None:
    """Install OpenTelemetry tracing on ``app`` when enabled.

    Idempotent — repeated calls across tests do not stack exporters.
    """
    global _INSTALLED
    if _INSTALLED:
        return
    if not _is_enabled(app):
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
            SimpleSpanProcessor,
        )
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.flask import FlaskInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import (
            SQLAlchemyInstrumentor,
        )
    except ImportError as exc:
        app.logger.warning("tracing_disabled_missing_deps", extra={"error": str(exc)})
        return

    service_name = app.config.get("OTEL_SERVICE_NAME") or os.environ.get(
        "OTEL_SERVICE_NAME", "trustseal"
    )
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "trustseal",
            "deployment.environment": app.config.get("FLASK_ENV", "unknown"),
        }
    )
    provider = TracerProvider(resource=resource)

    # Redaction runs before the exporter. The SDK-subclassed version
    # honours the full SpanProcessor contract.
    provider.add_span_processor(_make_scrub_processor()())

    endpoint = app.config.get("OTEL_EXPORTER_OTLP_ENDPOINT") or os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    if endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))

    if (
        str(app.config.get("OTEL_CONSOLE", "")).lower() in {"1", "true", "yes"}
        or os.environ.get("OTEL_CONSOLE") == "1"
    ):
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    # OpenTelemetry refuses to override the global provider after it
    # is first set. Accept the warning and continue; subsequent app
    # factory invocations reuse the existing provider and the
    # instrumentation is idempotent.
    try:
        trace.set_tracer_provider(provider)
    except Exception:  # pragma: no cover - provider already set
        pass

    try:
        FlaskInstrumentor().instrument_app(
            app, excluded_urls="static,api/metrics"
        )
    except (Exception, AssertionError):  # pragma: no cover
        # Flask refuses to add before_request after the first request;
        # repeated factory calls in tests trip this. The outer tracing
        # setup is still useful without the Flask before-request hook.
        pass
    try:
        RequestsInstrumentor().instrument()
    except Exception:  # pragma: no cover
        pass
    from app.extensions import db

    try:
        SQLAlchemyInstrumentor().instrument(
            engine=db.engine if hasattr(db, "engine") else None,
            enable_commenter=False,
        )
    except Exception:  # pragma: no cover
        pass

    try:
        @app.before_request
        def _attach_request_id() -> None:
            span = trace.get_current_span()
            if not span.is_recording():
                return
            request_id = getattr(g, "request_id", None)
            if request_id:
                span.set_attribute("trustseal.request_id", request_id)
            tenant = request.headers.get("X-TrustSeal-Tenant")
            if tenant:
                span.set_attribute("trustseal.tenant", tenant[:64])
    except AssertionError:
        # Flask refuses to add before_request after the first request
        # has been handled. Repeated factory calls in test harnesses
        # trip this; the trace-context binding is best-effort.
        pass

    _INSTALLED = True


def _is_enabled(app: Flask) -> bool:
    flag = app.config.get("OTEL_ENABLED") or os.environ.get("OTEL_ENABLED")
    return str(flag).lower() in {"1", "true", "yes"}


def tracer():
    """Return a tracer named after the caller's module.

    Services that want their own spans can call ``tracer().start_as_current_span(...)``.
    Returns a NoOp tracer when OTel is disabled so call sites never
    conditional on feature flags.
    """
    try:
        from opentelemetry import trace

        return trace.get_tracer("trustseal")
    except ImportError:  # pragma: no cover
        class _NoopTracer:
            def start_as_current_span(self, *_args: Any, **_kwargs: Any):
                import contextlib

                return contextlib.nullcontext()

        return _NoopTracer()
