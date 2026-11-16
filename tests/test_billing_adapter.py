"""Billing provider abstraction + in-memory adapter (I5)."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_memory_provider(pg_app):
    from app.services.billing import PROVIDERS

    PROVIDERS["memory"].reset()
    yield
    PROVIDERS["memory"].reset()


class TestInMemoryProvider:
    def test_create_customer_idempotent(self, pg_app):
        from app.services.billing import active_provider

        provider = active_provider()
        first = provider.create_customer(1, "alpha@example.test", "Alpha")
        second = provider.create_customer(1, "alpha@example.test", "Alpha")
        assert first == second
        assert len(provider.customers) == 1

    def test_create_customer_rejects_bad_email(self, pg_app):
        from app.services.billing import BillingError, active_provider

        with pytest.raises(BillingError):
            active_provider().create_customer(1, "no-at-sign", "x")

    def test_start_checkout_requires_customer(self, pg_app):
        from app.services.billing import BillingError, active_provider

        with pytest.raises(BillingError):
            active_provider().start_checkout(
                99,
                plan_id=1,
                success_url="http://localhost/success",
                cancel_url="http://localhost/cancel",
            )

    def test_start_checkout_returns_redirect_url(self, pg_app):
        from app.services.billing import active_provider

        provider = active_provider()
        provider.create_customer(1, "a@example.test", "A")
        session = provider.start_checkout(
            1,
            plan_id=42,
            success_url="http://localhost/success",
            cancel_url="http://localhost/cancel",
        )
        assert session.redirect_url.startswith("http://localhost/success")
        assert session.plan_id == 42
        assert len(provider.sessions) == 1

    def test_record_usage(self, pg_app):
        from app.services.billing import active_provider

        provider = active_provider()
        provider.record_usage(1, "envelope.prepared", 5)
        assert provider.usage == [
            {"organization_id": 1, "meter": "envelope.prepared", "hits": 5}
        ]

    def test_record_usage_rejects_nonpositive(self, pg_app):
        from app.services.billing import BillingError, active_provider

        with pytest.raises(BillingError):
            active_provider().record_usage(1, "m", 0)

    def test_cancel_records_reason(self, pg_app):
        from app.services.billing import active_provider

        provider = active_provider()
        provider.cancel_subscription(1, reason="customer_request")
        assert provider.cancellations == [
            {"organization_id": 1, "reason": "customer_request"}
        ]


class TestRegistry:
    def test_unknown_provider_raises(self, pg_app):
        from app.services.billing import BillingError, active_provider

        pg_app.config["BILLING_PROVIDER"] = "stripe-not-installed"
        try:
            with pytest.raises(BillingError):
                active_provider()
        finally:
            pg_app.config["BILLING_PROVIDER"] = "memory"

    def test_register_new_provider(self, pg_app):
        from app.services.billing import (
            BillingProvider,
            CheckoutSession,
            active_provider,
            register_provider,
        )

        class FakeAlt(BillingProvider):
            name = "fake-alt"

            def create_customer(self, organization_id, email, name=None):
                return "fake-cust"

            def start_checkout(
                self, organization_id, plan_id, *, success_url, cancel_url
            ):
                return CheckoutSession(
                    session_id="fake-sess",
                    redirect_url=success_url,
                    plan_id=plan_id,
                )

            def record_usage(self, organization_id, meter, hits):
                return None

            def cancel_subscription(self, organization_id, reason=None):
                return None

        register_provider(FakeAlt())
        pg_app.config["BILLING_PROVIDER"] = "fake-alt"
        try:
            provider = active_provider()
            assert provider.name == "fake-alt"
            assert provider.create_customer(1, "x@example.test") == "fake-cust"
        finally:
            pg_app.config["BILLING_PROVIDER"] = "memory"
