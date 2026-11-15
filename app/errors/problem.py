"""RFC 7807 ``application/problem+json`` responses.

Every API error (any request under ``/api/``) is returned as a problem
document with the following fields:

* ``type``      — URI identifying the problem kind. Opaque identifiers
                 under ``https://trustseal.dev/problems/<slug>`` so that
                 clients can switch on a stable string without parsing
                 ``title``.
* ``title``     — one-sentence human description. Stable per ``type``.
* ``status``    — HTTP status code (duplicated so JSON consumers do not
                 need to inspect headers).
* ``detail``    — optional per-instance context. **Never** includes raw
                 traceback, SQL, user-supplied payload content, tokens,
                 personal data, or storage paths.
* ``instance``  — the request path. Not a URI; identifies the specific
                 occurrence for log correlation.
* ``request_id``— from ``g.request_id`` when present. Lets callers quote
                 it to support without leaking traceback detail.

The module exposes :func:`problem_response` for ad-hoc raises and
:func:`register_problem_handlers` to install the global error handlers
on a Flask application. Legacy ``flask.abort(400, description=...)``
calls are translated transparently so existing code paths do not need
to be rewritten in lock-step.
"""
from __future__ import annotations

from typing import Any, Mapping

from flask import Flask, Response, current_app, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from app.extensions import db

PROBLEM_CONTENT_TYPE = "application/problem+json"
TYPE_PREFIX = "https://trustseal.dev/problems/"

_STATUS_DEFAULTS: dict[int, tuple[str, str]] = {
    400: ("bad-request", "The request was not understood."),
    401: ("unauthorized", "Authentication is required."),
    403: ("forbidden", "The caller is not permitted to perform this action."),
    404: ("not-found", "The requested resource does not exist."),
    405: ("method-not-allowed", "The HTTP method is not allowed on this resource."),
    409: ("conflict", "The request conflicts with the current state."),
    410: ("gone", "The resource has been retired and will not return."),
    413: ("payload-too-large", "The request body exceeds the configured limit."),
    415: ("unsupported-media-type", "The request body media type is not supported."),
    422: ("validation-failed", "The request violated a validation rule."),
    429: ("too-many-requests", "The caller exceeded the allowed request rate."),
    500: ("internal-error", "The server encountered an unexpected condition."),
    503: ("service-unavailable", "A dependency is temporarily unavailable."),
}


def _slug_for(status: int, description: Any) -> tuple[str, str]:
    """Return ``(slug, title)`` for ``status`` and the optional detail.

    Legacy routes raise ``abort(status, description="...")`` with a
    short machine-ish description. When the description is a short
    kebab-identifier, promote it to the ``type`` slug so clients can
    discriminate without inspecting the free-text ``detail``.
    """
    default_slug, default_title = _STATUS_DEFAULTS.get(
        status, ("error", "An error occurred.")
    )
    if isinstance(description, str) and description:
        lowered = description.strip().lower()
        # Promote only short, alphanumeric/underscore/hyphen strings. A
        # long free-form message stays in ``detail`` and the default slug
        # applies.
        if 1 < len(lowered) <= 64 and lowered.replace("_", "").replace("-", "").isalnum():
            return lowered.replace("_", "-"), default_title
    return default_slug, default_title


def _detail_for(description: Any) -> str | None:
    """Return a safe ``detail`` string, or ``None`` if the hint is a slug.

    Avoids echoing raw framework defaults like
    ``"The browser (or proxy) sent a request..."`` because they leak
    nothing useful and crowd the response.
    """
    if not isinstance(description, str) or not description:
        return None
    lowered = description.strip().lower()
    if 1 < len(lowered) <= 64 and lowered.replace("_", "").replace("-", "").isalnum():
        return None
    # Werkzeug default descriptions echo client intent, not server state.
    framework_prefixes = (
        "The browser",
        "The server",
        "The requested URL",
        "The method is not allowed",
        "You should not", "You don't have",
        "The request",
    )
    if any(description.startswith(prefix) for prefix in framework_prefixes):
        return None
    return description


def problem_response(
    status: int,
    *,
    slug: str | None = None,
    title: str | None = None,
    detail: str | None = None,
    extensions: Mapping[str, Any] | None = None,
) -> Response:
    """Build a canonical problem+json response.

    Call this from view code when a structured, stable problem type is
    known in advance:

        return problem_response(409, slug="envelope_not_prepared")
    """
    default_slug, default_title = _STATUS_DEFAULTS.get(
        status, ("error", "An error occurred.")
    )
    final_slug = (slug or default_slug).replace("_", "-")
    document: dict[str, Any] = {
        "type": TYPE_PREFIX + final_slug,
        "title": title or default_title,
        "status": int(status),
        "instance": request.path,
    }
    if detail:
        document["detail"] = detail
    request_id = getattr(g, "request_id", None)
    if request_id:
        document["request_id"] = request_id
    if extensions:
        for key, value in extensions.items():
            if key in document:
                continue
            document[key] = value
    response = jsonify(document)
    response.status_code = int(status)
    response.content_type = PROBLEM_CONTENT_TYPE
    response.headers["Cache-Control"] = "no-store"
    return response


def _register_jwt_problem_callbacks(app: Flask) -> None:
    """Route flask_jwt_extended errors through the problem+json shape.

    flask_jwt_extended installs its own JSON callbacks at init; those
    emit ``application/json`` and bypass the Flask error handler stack.
    We override each callback so authentication failures expose the
    stable problem types clients already discover from other endpoints.
    """
    from app.extensions import jwt

    @jwt.unauthorized_loader
    def _missing(_reason):
        return problem_response(
            401, slug="missing-authentication", detail="Authentication required."
        )

    @jwt.invalid_token_loader
    def _invalid(_reason):
        return problem_response(
            401, slug="invalid-token", detail="The authentication token is not valid."
        )

    @jwt.expired_token_loader
    def _expired(_header, _payload):
        return problem_response(
            401, slug="expired-token", detail="The authentication token has expired."
        )

    @jwt.revoked_token_loader
    def _revoked(_header, _payload):
        return problem_response(
            401, slug="revoked-token", detail="The authentication token was revoked."
        )

    @jwt.needs_fresh_token_loader
    def _stale(_header, _payload):
        return problem_response(
            401,
            slug="fresh-token-required",
            detail="A freshly authenticated session is required.",
        )


def register_problem_handlers(app: Flask) -> None:
    """Install the RFC 7807 handlers and the HTML fallbacks.

    HTML pages for authenticated views (anything outside ``/api/``) keep
    rendering through Jinja templates to preserve the existing UX. API
    callers always get problem+json.
    """
    _register_jwt_problem_callbacks(app)

    @app.errorhandler(HTTPException)
    def _http_exception(error: HTTPException):
        path = request.path or ""
        is_api = path.startswith("/api/")
        if not is_api:
            if error.code == 401:
                from flask import flash, redirect, url_for

                flash("Authorization is required to access this page.", "warning")
                return redirect(url_for("auth_views.login"))
            if error.code == 403:
                return render_template("errors/403.html"), 403
            if error.code == 404:
                return render_template("errors/404.html"), 404
            if error.code and 500 <= error.code < 600:
                db.session.rollback()
                current_app.logger.exception(
                    "Unhandled server error on %s", request.path
                )
                return render_template("errors/500.html", error_info=None), error.code
            return error  # Let Werkzeug render its default page.
        description = getattr(error, "description", None)
        slug, title = _slug_for(int(error.code or 500), description)
        detail = _detail_for(description)
        return problem_response(
            int(error.code or 500), slug=slug, title=title, detail=detail
        )

    @app.errorhandler(500)
    def _unhandled_500(error):
        db.session.rollback()
        current_app.logger.exception("Unhandled server error on %s", request.path)
        if (request.path or "").startswith("/api/"):
            return problem_response(500)
        return render_template("errors/500.html", error_info=None), 500

    @app.errorhandler(Exception)
    def _unhandled_exception(error):
        # Werkzeug-wrapped exceptions are handled above; this catches
        # any plain Python exception that escaped a view.
        if isinstance(error, HTTPException):
            return _http_exception(error)
        db.session.rollback()
        current_app.logger.exception("Unhandled exception on %s", request.path)
        if (request.path or "").startswith("/api/"):
            return problem_response(500)
        return render_template("errors/500.html", error_info=None), 500
