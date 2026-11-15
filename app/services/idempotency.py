"""Request-level idempotency for trust-critical mutations.

Contract (ADR 0004):

* Decorated endpoints require the ``Idempotency-Key`` header (400 otherwise).
* On first use, a row is inserted in ``idempotency_records`` with
  ``state = 'locked'``. If the view returns a 2xx response, the row is
  updated to ``state = 'completed'`` with the serialized response.
* A repeated request with the same key replays the stored response.
* A repeated request whose body hash differs from the stored row returns
  409 ``idempotency_key_body_conflict``.
* A repeated request arriving while the row is still locked returns 409
  with ``Retry-After``.

The guarantee is per-tenant. The decorator is a no-op for anonymous
callers because they have no tenant; the caller is expected to compose
``@jwt_required`` or ``@require_policy`` first.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable

from flask import Response, abort, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.idempotency_record import IdempotencyRecord
from app.models.user import User

DEFAULT_TTL = timedelta(hours=24)


def _tenant_for_request() -> int:
    """Resolve the current caller's tenant.

    Uses the JWT identity to load ``User.organization_id``. The decorator
    aborts 401 if the caller is anonymous; it aborts 409 if the caller has
    no tenant (idempotency is per-tenant; untenanted callers have no
    well-defined collision space).
    """
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        abort(401)
    user = User.query.get(user_id)
    if user is None or not user.is_active:
        abort(401)
    if user.organization_id is None:
        abort(409, description="idempotency_requires_tenant")
    return int(user.organization_id)


def _hash_body(body: bytes) -> str:
    return hashlib.sha256(body or b"").hexdigest()


def _canonical_body() -> bytes:
    """Return a stable byte representation of the request body.

    JSON bodies are re-serialized with sorted keys so insignificant
    reorderings do not produce a false ``body_conflict``. Non-JSON bodies
    are hashed verbatim.
    """
    if request.is_json:
        try:
            payload = request.get_json(silent=False)
        except Exception:
            return request.get_data() or b""
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return request.get_data() or b""


def _replay(record: IdempotencyRecord) -> Response:
    body = record.response_body if record.response_body is not None else {}
    response = jsonify(body)
    response.status_code = int(record.response_status or 200)
    headers = record.response_headers or {}
    if isinstance(headers, dict):
        for k, v in headers.items():
            if isinstance(k, str) and isinstance(v, (str, int, float)):
                response.headers[k] = str(v)
    response.headers["Idempotent-Replay"] = "true"
    return response


def _serialize(response: Response) -> tuple[int, Any, dict[str, str]]:
    try:
        body = response.get_json(silent=True)
    except Exception:
        body = None
    if body is None:
        # Non-JSON responses cannot be replayed safely; store an empty body
        # and the status only. Decorators should only wrap JSON endpoints.
        body = {}
    exclude = {"Content-Length", "Content-Type", "Idempotent-Replay"}
    headers = {k: v for k, v in response.headers.items() if k not in exclude}
    return int(response.status_code), body, headers


def idempotent(endpoint: str, *, ttl: timedelta = DEFAULT_TTL) -> Callable[[Callable], Callable]:
    """Decorator for POST/PUT/PATCH trust-critical mutations.

    ``endpoint`` must be a stable string (``"envelopes.finalize"`` rather
    than the raw URL) so uniqueness holds across version prefixes and
    path templates.
    """

    def wrap(view: Callable) -> Callable:
        @wraps(view)
        def inner(*args: Any, **kwargs: Any):
            key = request.headers.get("Idempotency-Key", "").strip()
            if not key:
                abort(400, description="idempotency_key_required")
            if len(key) > 128:
                abort(400, description="idempotency_key_too_long")
            tenant_id = _tenant_for_request()
            body_bytes = _canonical_body()
            request_hash = _hash_body(body_bytes)

            existing = (
                IdempotencyRecord.query.filter_by(
                    tenant_id=tenant_id, endpoint=endpoint, key=key
                ).first()
            )
            if existing is not None:
                if existing.request_hash != request_hash:
                    abort(409, description="idempotency_key_body_conflict")
                if existing.state == "completed":
                    return _replay(existing)
                if existing.state == "locked":
                    response = jsonify({"error": "idempotency_in_progress"})
                    response.status_code = 409
                    response.headers["Retry-After"] = "1"
                    return response
                # 'failed' falls through — allow a retry on the same key.
            now = datetime.utcnow()
            record = IdempotencyRecord(
                tenant_id=tenant_id,
                endpoint=endpoint,
                key=key,
                request_hash=request_hash,
                state="locked",
                locked_at=now,
                expires_at=now + ttl,
            )
            db.session.add(record)
            try:
                db.session.flush()
            except IntegrityError:
                db.session.rollback()
                # Another request raced us to insert; resolve by reading.
                existing = (
                    IdempotencyRecord.query.filter_by(
                        tenant_id=tenant_id, endpoint=endpoint, key=key
                    ).first()
                )
                if existing is None:
                    abort(500, description="idempotency_race_lost")
                if existing.request_hash != request_hash:
                    abort(409, description="idempotency_key_body_conflict")
                if existing.state == "completed":
                    return _replay(existing)
                response = jsonify({"error": "idempotency_in_progress"})
                response.status_code = 409
                response.headers["Retry-After"] = "1"
                return response

            try:
                result = view(*args, **kwargs)
            except Exception:
                record.state = "failed"
                db.session.commit()
                raise

            response = current_app.make_response(result)
            if 200 <= response.status_code < 300:
                status, body, headers = _serialize(response)
                record.state = "completed"
                record.response_status = status
                record.response_body = body
                record.response_headers = headers
                record.completed_at = datetime.utcnow()
            else:
                record.state = "failed"
                record.response_status = int(response.status_code)
            db.session.commit()
            return response

        return inner

    return wrap


def prune_expired(now: datetime | None = None) -> int:
    """Delete idempotency records past their expiration.

    Returns the number of rows removed. Intended to be invoked from the
    retention CLI; never from a web request.
    """
    threshold = now or datetime.utcnow()
    removed = (
        IdempotencyRecord.query.filter(IdempotencyRecord.expires_at < threshold).delete(
            synchronize_session=False
        )
    )
    db.session.commit()
    return int(removed)
