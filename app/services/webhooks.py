"""Signed, replay-protected webhook dispatch.

Design (ADR-grade, not a scaffold):

* Endpoints are tenant-scoped. Each endpoint carries a secret used to
  sign deliveries. The raw secret is shown to the operator exactly
  once; only a SHA-256 hash is persisted so a database compromise does
  not leak outbound signing material.
* Every delivery is an append-only row. The dispatcher claims a batch
  of eligible pending/failed deliveries, moves them to ``in_flight``,
  performs the HTTP POST with a timeout, and settles the row to
  ``succeeded`` or ``failed``. Failures reschedule with exponential
  backoff and cap at :data:`MAX_RETRIES` before transitioning to
  ``dead``.
* Signatures are canonical: ``X-TrustSeal-Signature: v1,ts=<unix>,sig=<hex>``
  where ``sig = HMAC_SHA256(secret, ts + "." + body)``. Receivers
  recompute and compare using a constant-time check. The timestamp
  must be within :data:`REPLAY_WINDOW_SECONDS` of the receiver's clock
  so a captured request cannot be replayed indefinitely.
* The outbox worker calls :func:`fan_out_event` when it processes an
  outbox event that has a configured webhook mapping.

HTTP calls go through :mod:`requests` with a strict timeout. In unit
tests we inject a transport callable so no real network is used.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Iterable

from sqlalchemy import or_

from app.extensions import db
from app.models.webhook import WebhookDelivery, WebhookEndpoint

MAX_RETRIES = 6
INITIAL_BACKOFF = timedelta(seconds=30)
MAX_BACKOFF = timedelta(hours=6)
REQUEST_TIMEOUT_SECONDS = 10
MAX_BODY_BYTES = 128 * 1024
REPLAY_WINDOW_SECONDS = 300
SIGNATURE_HEADER = "X-TrustSeal-Signature"


class WebhookError(RuntimeError):
    """Domain-level failure for webhook operations."""


@dataclass(frozen=True)
class DeliveryAttempt:
    status_code: int | None
    response_excerpt: str
    error: str | None


# A transport is any callable with the ``requests.post`` signature
# fragment we use. Keeps the dispatcher testable without monkey-patching
# the global ``requests`` module.
Transport = Callable[..., "HttpResponse"]


class HttpResponse:  # pragma: no cover - interface documentation only
    status_code: int
    text: str


# ---------------------------------------------------------------- helpers


def _is_valid_event_pattern(pattern: str) -> bool:
    """Validate a subscription pattern.

    Accepted shapes:
      * ``"*"``         — match every event type.
      * ``"prefix.*"``  — match ``prefix.<something>`` (prefix non-empty,
                           contains no inner ``*``).
      * ``"x.y.z"``     — exact event-type string. Must contain only
                           alnum, dot, underscore, or dash.
    """
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        prefix = pattern[:-2]
        if not prefix or "*" in prefix:
            return False
        return all(ch.isalnum() or ch in "._-" for ch in prefix)
    if "*" in pattern:
        return False
    return all(ch.isalnum() or ch in "._-" for ch in pattern)


def _event_matches(event_type: str, patterns: list[str]) -> bool:
    """Return ``True`` if ``event_type`` satisfies any subscription pattern."""
    for pattern in patterns:
        if pattern == "*":
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            if event_type.startswith(prefix + "."):
                return True
            continue
        if event_type == pattern:
            return True
    return False


def _hash_secret(secret: str) -> str:
    """Return a hex digest of the secret for at-rest storage."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def generate_secret() -> str:
    """Return a 256-bit URL-safe HMAC secret."""
    return "whsec_" + secrets.token_urlsafe(32)


def sign_payload(secret: str, timestamp: int, body: bytes) -> str:
    """Compute the canonical signature header value.

    Receivers independently compute this and constant-time compare.
    """
    base = f"{timestamp}.".encode("ascii") + body
    mac = hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    return f"v1,ts={timestamp},sig={mac}"


def verify_signature(
    secret: str, header_value: str, body: bytes, *, now: int, window: int = REPLAY_WINDOW_SECONDS
) -> bool:
    """Verify an incoming signature header.

    Returns True only when the version matches, the timestamp is within
    ``window`` seconds of ``now``, and the HMAC matches in constant time.
    """
    if not header_value:
        return False
    try:
        parts = dict(item.split("=", 1) for item in header_value.split(",") if "=" in item)
    except ValueError:
        return False
    version_present = any(p.strip() == "v1" for p in header_value.split(","))
    if not version_present:
        return False
    ts_raw = parts.get("ts")
    sig = parts.get("sig")
    if not ts_raw or not sig:
        return False
    try:
        ts = int(ts_raw)
    except ValueError:
        return False
    if abs(now - ts) > window:
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{ts}.".encode("ascii") + body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, sig)


# ---------------------------------------------------------------- endpoint API


def register_endpoint(
    *,
    tenant_id: int,
    created_by_id: int,
    url: str,
    events: Iterable[str],
    description: str | None = None,
) -> tuple[WebhookEndpoint, str]:
    """Create a new webhook endpoint and return the generated secret.

    The caller MUST surface the returned secret to the operator exactly
    once; it is not retrievable later.
    """
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise WebhookError("webhook URL must be absolute http(s)")
    if len(url) > 512:
        raise WebhookError("webhook URL exceeds 512 characters")
    event_list = [str(e).strip() for e in events if str(e).strip()]
    if not event_list:
        raise WebhookError("at least one event type must be subscribed")
    if any(len(e) > 80 for e in event_list):
        raise WebhookError("event type exceeds 80 characters")
    for pattern in event_list:
        if not _is_valid_event_pattern(pattern):
            raise WebhookError(
                "event type must be an exact type, \"*\", or a \"prefix.*\" wildcard"
            )
    if WebhookEndpoint.query.filter_by(
        organization_id=tenant_id, url=url
    ).first():
        raise WebhookError("duplicate webhook URL for this tenant")
    secret = generate_secret()
    endpoint = WebhookEndpoint(
        organization_id=tenant_id,
        created_by_id=created_by_id,
        url=url,
        secret_hash=_hash_secret(secret),
        events=event_list,
        active=True,
        description=(description or "")[:200] or None,
    )
    db.session.add(endpoint)
    db.session.flush()
    return endpoint, secret


def rotate_secret(endpoint: WebhookEndpoint) -> str:
    """Rotate an endpoint's secret and return the new value."""
    secret = generate_secret()
    endpoint.secret_hash = _hash_secret(secret)
    endpoint.updated_at = datetime.utcnow()
    db.session.flush()
    return secret


def deactivate(endpoint: WebhookEndpoint) -> None:
    endpoint.active = False
    endpoint.updated_at = datetime.utcnow()
    db.session.flush()


# ---------------------------------------------------------------- dispatch


def fan_out_event(
    *,
    tenant_id: int,
    event_id: str,
    event_type: str,
    payload: dict,
) -> list[WebhookDelivery]:
    """Enqueue one :class:`WebhookDelivery` per matching active endpoint.

    No HTTP I/O happens here. Attempts are made asynchronously by
    :func:`dispatch_due`.
    """
    if not isinstance(event_id, str) or not event_id or len(event_id) > 64:
        raise WebhookError("event_id must be a non-empty string under 64 chars")
    if not isinstance(event_type, str) or not event_type or len(event_type) > 80:
        raise WebhookError("event_type must be a non-empty string under 80 chars")
    endpoints = WebhookEndpoint.query.filter_by(
        organization_id=tenant_id, active=True
    ).all()
    deliveries: list[WebhookDelivery] = []
    now = datetime.utcnow()
    for endpoint in endpoints:
        if not _event_matches(event_type, endpoint.events or []):
            continue
        # Idempotent per (endpoint, event_id) — a repeated fan-out does
        # not create a second delivery row.
        existing = WebhookDelivery.query.filter_by(
            endpoint_id=endpoint.id, event_id=event_id
        ).first()
        if existing is not None:
            deliveries.append(existing)
            continue
        delivery = WebhookDelivery(
            endpoint_id=endpoint.id,
            organization_id=tenant_id,
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            status="pending",
            retry_count=0,
            next_retry_at=now,
            created_at=now,
        )
        db.session.add(delivery)
        deliveries.append(delivery)
    db.session.flush()
    return deliveries


def enqueue_ping(endpoint: WebhookEndpoint) -> WebhookDelivery:
    """Create a synthetic ``trustseal.ping`` delivery for one endpoint.

    Bypasses event-type subscription so operators can test an endpoint
    they just registered before any real event fires.
    """
    import uuid as _uuid

    now = datetime.utcnow()
    event_id = "ping-" + _uuid.uuid4().hex[:24]
    delivery = WebhookDelivery(
        endpoint_id=endpoint.id,
        organization_id=endpoint.organization_id,
        event_id=event_id,
        event_type="trustseal.ping",
        payload={
            "message": "TrustSeal webhook connectivity probe.",
            "endpoint_id": endpoint.id,
            "sent_at": now.isoformat(),
        },
        status="pending",
        retry_count=0,
        next_retry_at=now,
        created_at=now,
    )
    db.session.add(delivery)
    db.session.flush()
    return delivery


def replay_delivery(original: WebhookDelivery) -> WebhookDelivery:
    """Create a fresh delivery that mirrors ``original``.

    Operator-triggered — used to re-fire after the target receiver has
    been fixed. The original row is preserved for audit; the replay
    gets a new ``event_id`` so the dispatcher treats it as a
    first-time attempt.
    """
    import uuid as _uuid

    now = datetime.utcnow()
    delivery = WebhookDelivery(
        endpoint_id=original.endpoint_id,
        organization_id=original.organization_id,
        event_id=f"replay:{original.id}:{_uuid.uuid4().hex[:16]}",
        event_type=original.event_type,
        payload={
            **(original.payload or {}),
            "trustseal_replay_of_delivery_id": original.id,
        },
        status="pending",
        retry_count=0,
        next_retry_at=now,
        created_at=now,
    )
    db.session.add(delivery)
    db.session.flush()
    return delivery


def _backoff(retry_count: int) -> timedelta:
    delay = INITIAL_BACKOFF * (2 ** max(0, retry_count))
    return min(delay, MAX_BACKOFF)


def _default_transport():
    import requests

    def _post(url: str, *, data: bytes, headers: dict[str, str], timeout: int):
        return requests.post(url, data=data, headers=headers, timeout=timeout)

    return _post


def dispatch_due(
    *,
    limit: int = 25,
    now: datetime | None = None,
    transport: Transport | None = None,
    secret_resolver: Callable[[WebhookEndpoint], str] | None = None,
) -> int:
    """Attempt delivery for up to ``limit`` due rows.

    ``secret_resolver`` is required in test contexts because the raw
    secret is not persisted; production callers wire a resolver backed
    by a configured secret vault. See
    ``docs/decisions/0001-key-rotation.md``.
    """
    import json

    if transport is None:
        transport = _default_transport()
    if secret_resolver is None:
        raise WebhookError(
            "secret_resolver is required; raw secrets are not stored in the database"
        )
    threshold = now or datetime.utcnow()
    rows = (
        WebhookDelivery.query.filter(
            or_(
                WebhookDelivery.status == "pending",
                WebhookDelivery.status == "failed",
            ),
            WebhookDelivery.next_retry_at <= threshold,
            WebhookDelivery.retry_count < MAX_RETRIES,
        )
        .order_by(WebhookDelivery.next_retry_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
        .all()
    )
    processed = 0
    for delivery in rows:
        delivery.status = "in_flight"
        delivery.sent_at = datetime.utcnow()
        db.session.flush()
        endpoint = db.session.get(WebhookEndpoint, delivery.endpoint_id)
        if endpoint is None or not endpoint.active:
            delivery.status = "dead"
            delivery.last_error = "endpoint missing or deactivated"
            delivery.completed_at = datetime.utcnow()
            db.session.commit()
            continue
        try:
            secret = secret_resolver(endpoint)
        except Exception as exc:
            delivery.status = "failed"
            delivery.retry_count += 1
            delivery.last_error = f"secret_unavailable: {exc}"[:400]
            delivery.next_retry_at = datetime.utcnow() + _backoff(delivery.retry_count)
            if delivery.retry_count >= MAX_RETRIES:
                delivery.status = "dead"
                delivery.completed_at = datetime.utcnow()
            db.session.commit()
            continue
        body_text = json.dumps(delivery.payload, sort_keys=True, separators=(",", ":"))
        body_bytes = body_text.encode("utf-8")[:MAX_BODY_BYTES]
        timestamp = int(datetime.utcnow().timestamp())
        signature = sign_payload(secret, timestamp, body_bytes)
        headers = {
            "Content-Type": "application/json",
            SIGNATURE_HEADER: signature,
            "X-TrustSeal-Event": delivery.event_type,
            "X-TrustSeal-Event-Id": delivery.event_id,
            "X-TrustSeal-Delivery-Id": str(delivery.id),
        }
        attempt = _attempt(transport, endpoint.url, body_bytes, headers)
        if attempt.status_code is not None and 200 <= attempt.status_code < 300:
            delivery.status = "succeeded"
            delivery.response_status = attempt.status_code
            delivery.response_excerpt = attempt.response_excerpt[:400] or None
            delivery.completed_at = datetime.utcnow()
            delivery.last_error = None
        else:
            delivery.retry_count += 1
            delivery.response_status = attempt.status_code
            delivery.response_excerpt = attempt.response_excerpt[:400] or None
            delivery.last_error = (attempt.error or "non-2xx response")[:400]
            if delivery.retry_count >= MAX_RETRIES:
                delivery.status = "dead"
                delivery.completed_at = datetime.utcnow()
            else:
                delivery.status = "failed"
                delivery.next_retry_at = datetime.utcnow() + _backoff(
                    delivery.retry_count
                )
        db.session.commit()
        processed += 1
    return processed


def _attempt(transport: Transport, url: str, body: bytes, headers: dict[str, str]) -> DeliveryAttempt:
    try:
        response = transport(
            url, data=body, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
        )
    except Exception as exc:
        return DeliveryAttempt(status_code=None, response_excerpt="", error=str(exc))
    text = getattr(response, "text", "") or ""
    return DeliveryAttempt(
        status_code=int(response.status_code),
        response_excerpt=text[:400],
        error=None,
    )
