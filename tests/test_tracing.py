"""OpenTelemetry tracing wire-up contract.

OpenTelemetry's global TracerProvider is a singleton that refuses
replacement after the first ``set_tracer_provider`` call. That makes
exercising the full enable/disable cycle in a pytest session
unreliable — the first test to instrument the Flask app wins and
subsequent tests inherit its state. We therefore test:

* The scrub processor redacts known-sensitive attributes.
* The tracer helper returns a usable context manager when OTel is
  disabled (NoOp tracer).
* ``configure_tracing`` is a no-op when ``OTEL_ENABLED`` is unset.
* ``configure_tracing`` executes without raising when OTel is
  enabled, exercising the full plumbing (instrumentation,
  processor, exporter attachment).

End-to-end verification against a real collector happens on staging,
not in unit tests. See ``docs/perf/overview.md`` and the deployment
runbook.
"""
from __future__ import annotations

import pytest


class TestScrubProcessor:
    def test_scrubs_auth_headers(self):
        from app.tracing import SCRUB_PLACEHOLDER, _ScrubProcessor

        class _FakeSpan:
            def __init__(self) -> None:
                self.attributes = {
                    "http.request.header.authorization": "Bearer secret",
                    "http.method": "POST",
                }
                self._attributes = dict(self.attributes)

        span = _FakeSpan()
        _ScrubProcessor().on_end(span)
        assert span._attributes["http.request.header.authorization"] == SCRUB_PLACEHOLDER
        assert span._attributes["http.method"] == "POST"

    def test_noop_on_start(self):
        from app.tracing import _ScrubProcessor

        _ScrubProcessor().on_start(None)
        _ScrubProcessor().shutdown()
        assert _ScrubProcessor().force_flush(0) is True


class TestDefaults:
    def test_tracer_works_when_disabled(self, pg_app):
        pg_app.config["OTEL_ENABLED"] = False
        from app.tracing import tracer

        with tracer().start_as_current_span("probe"):
            pass  # exercise the context manager path

    def test_configure_is_noop_when_disabled(self, pg_app):
        pg_app.config.pop("OTEL_ENABLED", None)
        import os as _os

        _os.environ.pop("OTEL_ENABLED", None)
        import app.tracing

        app.tracing._INSTALLED = False
        app.tracing.configure_tracing(pg_app)
        assert app.tracing._INSTALLED is False


class TestEnablement:
    def test_configure_with_opt_in_runs_without_raising(self, pg_app):
        """When ``OTEL_ENABLED=1`` is set, configure must boot cleanly.

        The function is intentionally forgiving of the OTel singleton:
        re-installing instrumentation across repeated calls raises an
        internal warning that ``configure_tracing`` swallows, preserving
        boot-time safety in container orchestrators that may re-run
        the Flask factory.
        """
        pg_app.config["OTEL_ENABLED"] = "1"
        pg_app.config.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
        pg_app.config.pop("OTEL_CONSOLE", None)
        import app.tracing

        app.tracing._INSTALLED = False
        try:
            app.tracing.configure_tracing(pg_app)
            # Flag may or may not flip depending on whether an earlier
            # test in the session already instrumented the shared app.
            # The contract we care about is "no exception".
        finally:
            app.tracing._INSTALLED = False
