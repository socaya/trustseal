"""Provider-agnostic billing abstraction.

Scope: the operator picks a provider (``BILLING_PROVIDER`` config);
the service layer talks to it through a narrow interface. The
in-memory reference adapter ships in-tree so unit tests exercise the
full lifecycle without a real payment provider.

Interface:

* ``create_customer(organization_id, email, name)`` — returns an
  opaque provider customer id.
* ``start_checkout(organization_id, plan_id, *, success_url,
  cancel_url)`` — returns a redirect URL the user is sent to.
* ``record_usage(organization_id, meter, hits)`` — reports metered
  usage for metered plans.
* ``cancel_subscription(organization_id, reason=None)`` — ends the
  current subscription (grace period is the provider's concern).

Adapters register themselves in :data:`PROVIDERS` so callers can
plug in Stripe / Paddle without touching the application. The
in-memory adapter captures every call so tests can assert on the
sequence of interactions.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from flask import current_app


class BillingError(RuntimeError):
    """Raised on policy or provider failure."""


@dataclass
class CheckoutSession:
    session_id: str
    redirect_url: str
    plan_id: int


class BillingProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def create_customer(
        self, organization_id: int, email: str, name: Optional[str] = None
    ) -> str: ...

    @abstractmethod
    def start_checkout(
        self,
        organization_id: int,
        plan_id: int,
        *,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSession: ...

    @abstractmethod
    def record_usage(
        self, organization_id: int, meter: str, hits: int
    ) -> None: ...

    @abstractmethod
    def cancel_subscription(
        self, organization_id: int, reason: Optional[str] = None
    ) -> None: ...


@dataclass
class InMemoryBillingProvider(BillingProvider):
    """Reference adapter — captures every call for tests."""

    name: str = "memory"
    customers: dict[int, dict] = field(default_factory=dict)
    sessions: list[CheckoutSession] = field(default_factory=list)
    usage: list[dict] = field(default_factory=list)
    cancellations: list[dict] = field(default_factory=list)

    def create_customer(
        self, organization_id: int, email: str, name: Optional[str] = None
    ) -> str:
        if not isinstance(email, str) or "@" not in email:
            raise BillingError("email_invalid")
        existing = self.customers.get(organization_id)
        if existing:
            return existing["id"]
        customer_id = f"cust_{uuid.uuid4().hex[:20]}"
        self.customers[organization_id] = {
            "id": customer_id,
            "email": email,
            "name": name,
        }
        return customer_id

    def start_checkout(
        self,
        organization_id: int,
        plan_id: int,
        *,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSession:
        if organization_id not in self.customers:
            raise BillingError("customer_not_found")
        session = CheckoutSession(
            session_id=f"sess_{uuid.uuid4().hex[:20]}",
            # The reference adapter just echoes back success_url with
            # the session id attached; real providers hand out a
            # hosted-checkout URL.
            redirect_url=(
                f"{success_url}?session_id={uuid.uuid4().hex[:20]}"
            ),
            plan_id=plan_id,
        )
        self.sessions.append(session)
        return session

    def record_usage(
        self, organization_id: int, meter: str, hits: int
    ) -> None:
        if hits <= 0:
            raise BillingError("hits_invalid")
        self.usage.append(
            {
                "organization_id": organization_id,
                "meter": meter,
                "hits": hits,
            }
        )

    def cancel_subscription(
        self, organization_id: int, reason: Optional[str] = None
    ) -> None:
        self.cancellations.append(
            {"organization_id": organization_id, "reason": reason}
        )

    # Test-only helpers ------------------------------------------------

    def reset(self) -> None:
        self.customers.clear()
        self.sessions.clear()
        self.usage.clear()
        self.cancellations.clear()


# Registry of available providers. Add real adapters (Stripe, Paddle)
# here and point ``BILLING_PROVIDER`` at their name. The in-memory
# reference adapter is the only one shipped in-tree.
PROVIDERS: dict[str, BillingProvider] = {
    "memory": InMemoryBillingProvider(),
}


def register_provider(provider: BillingProvider) -> None:
    PROVIDERS[provider.name] = provider


def active_provider() -> BillingProvider:
    """Return the provider selected by ``BILLING_PROVIDER``."""
    name = (current_app.config.get("BILLING_PROVIDER") or "memory").lower()
    provider = PROVIDERS.get(name)
    if provider is None:
        raise BillingError(f"unknown_provider:{name}")
    return provider
