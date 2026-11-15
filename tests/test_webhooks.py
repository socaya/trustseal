"""Webhook dispatcher contract.

Covers:

* HMAC signature generation and constant-time verification.
* Replay-protection: a captured request outside the window is rejected.
* ``register_endpoint`` persists only the hash of the secret.
* Duplicate URL per tenant is refused.
* ``fan_out_event`` is idempotent per (endpoint, event_id).
* The dispatcher attempts delivery and on 2xx marks the row
  ``succeeded``; on 5xx it schedules an exponential retry; after
  :data:`MAX_RETRIES` it transitions to ``dead``.
* Only active endpoints receive deliveries.
* Invalid URLs are refused at registration time.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest

from app.services import webhooks


# --- fixtures -------------------------------------------------------


@pytest.fixture
def tenant(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.user import User

    org = Organization(name="Webhook Tenant")
    db.session.add(org)
    db.session.flush()
    user = User(
        username="wh-admin", email="wh@example.test",
        is_active=True, organization_id=org.id,
    )
    user.set_password("not-used")
    db.session.add(user)
    db.session.commit()
    return {"org": org, "user": user}


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "ok"):
        self.status_code = status_code
        self.text = text


def _ok_transport(**_kwargs):
    def _post(url, *, data, headers, timeout):
        return _FakeResponse(200, "accepted")

    return _post


def _server_error_transport():
    def _post(url, *, data, headers, timeout):
        return _FakeResponse(503, "unavailable")

    return _post


# --- signing --------------------------------------------------------


class TestSignatureProtocol:
    def test_round_trip(self):
        secret = "whsec_test_round_trip"
        ts = 1_700_000_000
        body = b'{"hello":"world"}'
        header = webhooks.sign_payload(secret, ts, body)
        assert webhooks.verify_signature(secret, header, body, now=ts)

    def test_window_rejects_stale_timestamp(self):
        secret = "whsec_window"
        ts = 1_700_000_000
        body = b'{"x":1}'
        header = webhooks.sign_payload(secret, ts, body)
        assert not webhooks.verify_signature(
            secret, header, body, now=ts + 10_000, window=300
        )

    def test_wrong_secret_fails(self):
        header = webhooks.sign_payload("whsec_a", 1_700_000_000, b"body")
        assert not webhooks.verify_signature(
            "whsec_b", header, b"body", now=1_700_000_000
        )

    def test_tampered_body_fails(self):
        secret = "whsec_tamper"
        header = webhooks.sign_payload(secret, 1_700_000_000, b"original")
        assert not webhooks.verify_signature(
            secret, header, b"different", now=1_700_000_000
        )

    def test_missing_version_rejected(self):
        header = "ts=1700000000,sig=deadbeef"
        assert not webhooks.verify_signature(
            "secret", header, b"body", now=1_700_000_000
        )


# --- registration ---------------------------------------------------


class TestRegistration:
    def test_register_returns_secret_and_hashes_at_rest(self, pg_app, tenant):
        endpoint, secret = webhooks.register_endpoint(
            tenant_id=tenant["org"].id,
            created_by_id=tenant["user"].id,
            url="https://example.test/hook",
            events=["envelope.prepared"],
        )
        assert secret.startswith("whsec_")
        assert endpoint.secret_hash != secret
        import hashlib

        assert endpoint.secret_hash == hashlib.sha256(secret.encode()).hexdigest()
        assert endpoint.events == ["envelope.prepared"]
        assert endpoint.active is True

    def test_duplicate_url_rejected(self, pg_app, tenant):
        webhooks.register_endpoint(
            tenant_id=tenant["org"].id,
            created_by_id=tenant["user"].id,
            url="https://example.test/hook",
            events=["envelope.prepared"],
        )
        with pytest.raises(webhooks.WebhookError):
            webhooks.register_endpoint(
                tenant_id=tenant["org"].id,
                created_by_id=tenant["user"].id,
                url="https://example.test/hook",
                events=["envelope.prepared"],
            )

    def test_invalid_url_rejected(self, pg_app, tenant):
        for bad in ["ftp://example.test/hook", "no-scheme", ""]:
            with pytest.raises(webhooks.WebhookError):
                webhooks.register_endpoint(
                    tenant_id=tenant["org"].id,
                    created_by_id=tenant["user"].id,
                    url=bad,
                    events=["envelope.prepared"],
                )

    def test_empty_events_rejected(self, pg_app, tenant):
        with pytest.raises(webhooks.WebhookError):
            webhooks.register_endpoint(
                tenant_id=tenant["org"].id,
                created_by_id=tenant["user"].id,
                url="https://example.test/empty",
                events=[],
            )

    def test_rotation_changes_hash(self, pg_app, tenant):
        endpoint, original = webhooks.register_endpoint(
            tenant_id=tenant["org"].id,
            created_by_id=tenant["user"].id,
            url="https://example.test/rot",
            events=["envelope.prepared"],
        )
        original_hash = endpoint.secret_hash
        new_secret = webhooks.rotate_secret(endpoint)
        assert new_secret != original
        assert endpoint.secret_hash != original_hash


# --- fan-out --------------------------------------------------------


class TestFanOut:
    def test_match_by_event_type(self, pg_app, tenant):
        _ep_match, _ = webhooks.register_endpoint(
            tenant_id=tenant["org"].id,
            created_by_id=tenant["user"].id,
            url="https://example.test/match",
            events=["envelope.prepared"],
        )
        _ep_other, _ = webhooks.register_endpoint(
            tenant_id=tenant["org"].id,
            created_by_id=tenant["user"].id,
            url="https://example.test/other",
            events=["stamp.pdf.issued"],
        )
        deliveries = webhooks.fan_out_event(
            tenant_id=tenant["org"].id,
            event_id="evt-1",
            event_type="envelope.prepared",
            payload={"envelope_id": 7},
        )
        assert len(deliveries) == 1
        assert deliveries[0].endpoint_id == _ep_match.id

    def test_repeat_event_id_is_idempotent(self, pg_app, tenant):
        webhooks.register_endpoint(
            tenant_id=tenant["org"].id,
            created_by_id=tenant["user"].id,
            url="https://example.test/idem",
            events=["envelope.prepared"],
        )
        first = webhooks.fan_out_event(
            tenant_id=tenant["org"].id,
            event_id="evt-same",
            event_type="envelope.prepared",
            payload={"a": 1},
        )
        second = webhooks.fan_out_event(
            tenant_id=tenant["org"].id,
            event_id="evt-same",
            event_type="envelope.prepared",
            payload={"a": 1},
        )
        assert first[0].id == second[0].id


# --- dispatch -------------------------------------------------------


class TestDispatch:
    def test_successful_delivery_marks_succeeded(self, pg_app, tenant):
        endpoint, secret = webhooks.register_endpoint(
            tenant_id=tenant["org"].id,
            created_by_id=tenant["user"].id,
            url="https://example.test/success",
            events=["envelope.prepared"],
        )
        webhooks.fan_out_event(
            tenant_id=tenant["org"].id,
            event_id="evt-ok",
            event_type="envelope.prepared",
            payload={"envelope_id": 1},
        )
        processed = webhooks.dispatch_due(
            transport=_ok_transport(),
            secret_resolver=lambda ep: secret,
        )
        assert processed == 1
        from app.models.webhook import WebhookDelivery

        row = WebhookDelivery.query.filter_by(event_id="evt-ok").first()
        assert row.status == "succeeded"
        assert row.response_status == 200
        assert row.completed_at is not None

    def test_server_error_schedules_retry(self, pg_app, tenant):
        endpoint, secret = webhooks.register_endpoint(
            tenant_id=tenant["org"].id,
            created_by_id=tenant["user"].id,
            url="https://example.test/retry",
            events=["envelope.prepared"],
        )
        webhooks.fan_out_event(
            tenant_id=tenant["org"].id,
            event_id="evt-retry",
            event_type="envelope.prepared",
            payload={"envelope_id": 2},
        )
        webhooks.dispatch_due(
            transport=_server_error_transport(),
            secret_resolver=lambda ep: secret,
        )
        from app.models.webhook import WebhookDelivery

        row = WebhookDelivery.query.filter_by(event_id="evt-retry").first()
        assert row.status == "failed"
        assert row.retry_count == 1
        assert row.next_retry_at > datetime.utcnow()
        assert row.response_status == 503

    def test_repeated_failure_transitions_to_dead(self, pg_app, tenant):
        endpoint, secret = webhooks.register_endpoint(
            tenant_id=tenant["org"].id,
            created_by_id=tenant["user"].id,
            url="https://example.test/dead",
            events=["envelope.prepared"],
        )
        webhooks.fan_out_event(
            tenant_id=tenant["org"].id,
            event_id="evt-dead",
            event_type="envelope.prepared",
            payload={"envelope_id": 3},
        )
        for _ in range(webhooks.MAX_RETRIES):
            webhooks.dispatch_due(
                transport=_server_error_transport(),
                secret_resolver=lambda ep: secret,
                now=datetime.utcnow() + timedelta(hours=24),
            )
        from app.models.webhook import WebhookDelivery

        row = WebhookDelivery.query.filter_by(event_id="evt-dead").first()
        assert row.status == "dead"
        assert row.retry_count >= webhooks.MAX_RETRIES

    def test_signature_header_included_on_request(self, pg_app, tenant):
        endpoint, secret = webhooks.register_endpoint(
            tenant_id=tenant["org"].id,
            created_by_id=tenant["user"].id,
            url="https://example.test/sign",
            events=["envelope.prepared"],
        )
        webhooks.fan_out_event(
            tenant_id=tenant["org"].id,
            event_id="evt-sign",
            event_type="envelope.prepared",
            payload={"envelope_id": 9},
        )
        captured: dict[str, Any] = {}

        def capture_transport(url, *, data, headers, timeout):
            captured["url"] = url
            captured["data"] = data
            captured["headers"] = headers
            return _FakeResponse(200)

        webhooks.dispatch_due(
            transport=capture_transport,
            secret_resolver=lambda ep: secret,
        )
        header_value = captured["headers"][webhooks.SIGNATURE_HEADER]
        assert header_value.startswith("v1,ts=")
        # Receiver-side verification succeeds:
        ts = int(header_value.split("ts=")[1].split(",")[0])
        assert webhooks.verify_signature(
            secret, header_value, captured["data"], now=ts
        )

    def test_secret_resolver_failure_counts_as_retry(self, pg_app, tenant):
        endpoint, secret = webhooks.register_endpoint(
            tenant_id=tenant["org"].id,
            created_by_id=tenant["user"].id,
            url="https://example.test/no-secret",
            events=["envelope.prepared"],
        )
        webhooks.fan_out_event(
            tenant_id=tenant["org"].id,
            event_id="evt-missing-secret",
            event_type="envelope.prepared",
            payload={"envelope_id": 11},
        )

        def failing_resolver(_ep):
            raise RuntimeError("vault down")

        webhooks.dispatch_due(
            transport=_ok_transport(),
            secret_resolver=failing_resolver,
        )
        from app.models.webhook import WebhookDelivery

        row = WebhookDelivery.query.filter_by(event_id="evt-missing-secret").first()
        assert row.status == "failed"
        assert "secret_unavailable" in (row.last_error or "")

    def test_inactive_endpoint_delivery_dies(self, pg_app, tenant):
        endpoint, secret = webhooks.register_endpoint(
            tenant_id=tenant["org"].id,
            created_by_id=tenant["user"].id,
            url="https://example.test/off",
            events=["envelope.prepared"],
        )
        webhooks.fan_out_event(
            tenant_id=tenant["org"].id,
            event_id="evt-off",
            event_type="envelope.prepared",
            payload={"envelope_id": 12},
        )
        webhooks.deactivate(endpoint)
        webhooks.dispatch_due(
            transport=_ok_transport(),
            secret_resolver=lambda ep: secret,
        )
        from app.models.webhook import WebhookDelivery

        row = WebhookDelivery.query.filter_by(event_id="evt-off").first()
        assert row.status == "dead"
