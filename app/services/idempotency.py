"""Request-level idempotency for trust-critical mutations.

Contract (ADR 0004):

* Decorated endpoints require the ``Idempotency-Key`` header (400 otherwise).
* On first use, an entry is acquired with ``state = 'locked'``. If the view
  returns a 2xx response, the entry is updated to ``state = 'completed'``
  with the serialized response.
* A repeated request with the same key replays the stored response.
* A repeated request whose body hash differs from the stored entry returns
  409 ``idempotency_key_body_conflict``.
* A repeated request arriving while the entry is still locked returns 409
  with ``Retry-After``.

The guarantee is per-tenant. The storage backend is pluggable via
:class:`IdempotencyRepository` (default: :class:`PostgresIdempotencyRepository`;
multi-region active-active deployments can configure
:class:`RedisIdempotencyRepository` via ``app.config["IDEMPOTENCY_REPOSITORY"]``).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Optional, Protocol, runtime_checkable

from flask import Response, abort, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.idempotency_record import IdempotencyRecord
from app.models.user import User

DEFAULT_TTL = timedelta(hours=24)


@dataclass(frozen=True)
class IdempotencyEntry:
    """Backend-agnostic snapshot of an idempotency record."""

    tenant_id: int
    endpoint: str
    key: str
    request_hash: str
    state: str  # "locked" | "completed" | "failed"
    response_status: Optional[int] = None
    response_body: Any = None
    response_headers: Optional[dict[str, str]] = None


@runtime_checkable
class IdempotencyRepository(Protocol):
    """Pluggable storage interface for single- or cross-region idempotency."""

    def get(
        self, *, tenant_id: int, endpoint: str, key: str
    ) -> Optional[IdempotencyEntry]:
        """Return an existing entry for ``(tenant_id, endpoint, key)``, if any."""

    def acquire(
        self,
        *,
        tenant_id: int,
        endpoint: str,
        key: str,
        request_hash: str,
        ttl: timedelta,
    ) -> tuple[bool, Any]:
        """Atomically acquire a ``locked`` entry.

        Returns ``(True, handle)`` when acquired, or ``(False, existing_entry)``
        when another request already holds or completed the key.
        """

    def complete(
        self,
        handle: Any,
        *,
        status: int,
        body: Any,
        headers: dict[str, str],
    ) -> None:
        """Mark the acquired entry as ``completed`` with the serialized response."""

    def fail(self, handle: Any, *, status: Optional[int] = None) -> None:
        """Mark the acquired entry as ``failed`` so the client may safely retry."""


class PostgresIdempotencyRepository:
    """Default durable PostgreSQL-backed idempotency repository."""

    @staticmethod
    def _to_entry(row: IdempotencyRecord) -> IdempotencyEntry:
        return IdempotencyEntry(
            tenant_id=row.tenant_id,
            endpoint=row.endpoint,
            key=row.key,
            request_hash=row.request_hash,
            state=row.state,
            response_status=row.response_status,
            response_body=row.response_body,
            response_headers=row.response_headers,
        )

    def get(
        self, *, tenant_id: int, endpoint: str, key: str
    ) -> Optional[IdempotencyEntry]:
        row = IdempotencyRecord.query.filter_by(
            tenant_id=tenant_id, endpoint=endpoint, key=key
        ).first()
        return self._to_entry(row) if row is not None else None

    def acquire(
        self,
        *,
        tenant_id: int,
        endpoint: str,
        key: str,
        request_hash: str,
        ttl: timedelta,
    ) -> tuple[bool, Any]:
        now = datetime.utcnow()
        existing = IdempotencyRecord.query.filter_by(
            tenant_id=tenant_id, endpoint=endpoint, key=key
        ).first()
        if existing is not None and existing.state == "failed":
            existing.request_hash = request_hash
            existing.state = "locked"
            existing.locked_at = now
            existing.expires_at = now + ttl
            existing.response_status = None
            existing.response_body = None
            existing.response_headers = None
            db.session.flush()
            return True, existing

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
            return True, record
        except IntegrityError:
            db.session.rollback()
            raced = IdempotencyRecord.query.filter_by(
                tenant_id=tenant_id, endpoint=endpoint, key=key
            ).first()
            return False, (self._to_entry(raced) if raced is not None else None)

    def complete(
        self,
        handle: IdempotencyRecord,
        *,
        status: int,
        body: Any,
        headers: dict[str, str],
    ) -> None:
        handle.state = "completed"
        handle.response_status = status
        handle.response_body = body
        handle.response_headers = headers
        handle.completed_at = datetime.utcnow()
        db.session.commit()

    def fail(self, handle: IdempotencyRecord, *, status: Optional[int] = None) -> None:
        handle.state = "failed"
        if status is not None:
            handle.response_status = int(status)
        db.session.commit()


class RedisIdempotencyRepository:
    """Cross-region active-active Redis-backed idempotency repository.

    Accepts any Redis client exposing ``get(key)`` and
    ``set(key, value, ex=..., nx=...)`` (e.g. ``redis.Redis`` or
    ``redis.cluster.RedisCluster``).
    """

    def __init__(self, client: Any, *, key_prefix: str = "trustseal:idem") -> None:
        self._client = client
        self._prefix = key_prefix.rstrip(":")

    def _redis_key(self, *, tenant_id: int, endpoint: str, key: str) -> str:
        return f"{self._prefix}:{tenant_id}:{endpoint}:{key}"

    def _decode(
        self, raw: Any, *, tenant_id: int, endpoint: str, key: str
    ) -> Optional[IdempotencyEntry]:
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        return IdempotencyEntry(
            tenant_id=tenant_id,
            endpoint=endpoint,
            key=key,
            request_hash=str(data.get("request_hash", "")),
            state=str(data.get("state", "locked")),
            response_status=data.get("response_status"),
            response_body=data.get("response_body"),
            response_headers=data.get("response_headers"),
        )

    def get(
        self, *, tenant_id: int, endpoint: str, key: str
    ) -> Optional[IdempotencyEntry]:
        rkey = self._redis_key(tenant_id=tenant_id, endpoint=endpoint, key=key)
        return self._decode(
            self._client.get(rkey),
            tenant_id=tenant_id,
            endpoint=endpoint,
            key=key,
        )

    def acquire(
        self,
        *,
        tenant_id: int,
        endpoint: str,
        key: str,
        request_hash: str,
        ttl: timedelta,
    ) -> tuple[bool, Any]:
        rkey = self._redis_key(tenant_id=tenant_id, endpoint=endpoint, key=key)
        ttl_seconds = max(1, int(ttl.total_seconds()))
        payload = json.dumps({"request_hash": request_hash, "state": "locked"})
        acquired = bool(self._client.set(rkey, payload, ex=ttl_seconds, nx=True))
        if acquired:
            return True, (rkey, request_hash, ttl_seconds)
        existing = self.get(tenant_id=tenant_id, endpoint=endpoint, key=key)
        if existing is not None and existing.state == "failed":
            self._client.set(rkey, payload, ex=ttl_seconds)
            return True, (rkey, request_hash, ttl_seconds)
        return False, existing

    def complete(
        self,
        handle: tuple[str, str, int],
        *,
        status: int,
        body: Any,
        headers: dict[str, str],
    ) -> None:
        rkey, request_hash, ttl_seconds = handle
        payload = json.dumps(
            {
                "request_hash": request_hash,
                "state": "completed",
                "response_status": int(status),
                "response_body": body,
                "response_headers": headers,
            }
        )
        self._client.set(rkey, payload, ex=ttl_seconds)

    def fail(
        self, handle: tuple[str, str, int], *, status: Optional[int] = None
    ) -> None:
        rkey, request_hash, ttl_seconds = handle
        payload = json.dumps(
            {
                "request_hash": request_hash,
                "state": "failed",
                "response_status": int(status) if status is not None else None,
            }
        )
        self._client.set(rkey, payload, ex=ttl_seconds)


_DEFAULT_REPO = PostgresIdempotencyRepository()


def get_idempotency_repository() -> IdempotencyRepository:
    """Return the configured repository, defaulting to PostgreSQL."""
    configured = current_app.config.get("IDEMPOTENCY_REPOSITORY")
    if configured is not None:
        return configured
    return _DEFAULT_REPO


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
    user = db.session.get(User, user_id)
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


def _replay(entry: IdempotencyEntry | IdempotencyRecord) -> Response:
    body = entry.response_body if entry.response_body is not None else {}
    response = jsonify(body)
    response.status_code = int(entry.response_status or 200)
    headers = entry.response_headers or {}
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


def _handle_existing(existing: IdempotencyEntry, request_hash: str) -> Optional[Response]:
    if existing.request_hash != request_hash:
        abort(409, description="idempotency_key_body_conflict")
    if existing.state == "completed":
        return _replay(existing)
    if existing.state == "locked":
        response = jsonify({"error": "idempotency_in_progress"})
        response.status_code = 409
        response.headers["Retry-After"] = "1"
        return response
    return None


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
            repo = get_idempotency_repository()

            existing = repo.get(tenant_id=tenant_id, endpoint=endpoint, key=key)
            if existing is not None:
                handled = _handle_existing(existing, request_hash)
                if handled is not None:
                    return handled

            acquired, handle_or_existing = repo.acquire(
                tenant_id=tenant_id,
                endpoint=endpoint,
                key=key,
                request_hash=request_hash,
                ttl=ttl,
            )
            if not acquired:
                if handle_or_existing is None:
                    abort(500, description="idempotency_race_lost")
                handled = _handle_existing(handle_or_existing, request_hash)
                if handled is not None:
                    return handled
                abort(409, description="idempotency_in_progress")

            handle = handle_or_existing
            try:
                result = view(*args, **kwargs)
            except Exception:
                repo.fail(handle)
                raise

            response = current_app.make_response(result)
            if 200 <= response.status_code < 300:
                status, body, headers = _serialize(response)
                repo.complete(handle, status=status, body=body, headers=headers)
            else:
                repo.fail(handle, status=int(response.status_code))
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
