"""Tenant-controlled AI suggestions.

Scope: TrustSeal does not ship a specific AI provider in-tree. This
module is the **mechanism** — an abstract :class:`AiSuggestionProvider`
plus a reference :class:`NoopAiSuggestionProvider` and a registry.
Operators plug in a real provider (OpenAI, Anthropic, local
inference, etc.) by implementing the ABC and calling
:func:`register_provider`.

Policy:

* Every suggestion request emits a :class:`SecurityEvent` with
  action ``ai.suggestion.requested`` so operators can audit what
  text is being sent to the configured provider.
* Tenants must explicitly opt in. The in-memory flag is
  ``Organization.ai_suggestions_enabled``; if the model column is
  not present, we fall back to the app-level
  ``AI_SUGGESTIONS_ENABLED`` flag. The service refuses when both
  are false.
* The provider receives only the text the user explicitly submits —
  never a whole document, never other tenants' content.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from flask import current_app

from app.extensions import db
from app.models.event_delivery import SecurityEvent


class AiSuggestionError(RuntimeError):
    """Raised for policy failures or provider errors."""


@dataclass(frozen=True)
class Suggestion:
    """One AI-authored suggestion the user may accept or reject."""

    text: str
    confidence: float
    rationale: str


class AiSuggestionProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def suggest(
        self,
        *,
        context: str,
        prompt: str,
        organization_id: int,
        user_id: int,
    ) -> list[Suggestion]:
        """Return zero or more suggestions for ``prompt`` given ``context``.

        Providers must never raise for ordinary "no suggestion"
        outcomes; return an empty list instead. Raising is reserved
        for provider-level failures (quota exceeded, network
        timeout).
        """


class NoopAiSuggestionProvider(AiSuggestionProvider):
    """Reference adapter — returns an empty list.

    Useful as a test stand-in and as a safe default for operators
    who have not yet configured a real provider.
    """

    name = "noop"

    def suggest(self, *, context, prompt, organization_id, user_id):
        return []


PROVIDERS: dict[str, AiSuggestionProvider] = {
    "noop": NoopAiSuggestionProvider(),
}


def register_provider(provider: AiSuggestionProvider) -> None:
    PROVIDERS[provider.name] = provider


def active_provider() -> AiSuggestionProvider:
    name = (current_app.config.get("AI_SUGGESTION_PROVIDER") or "noop").lower()
    provider = PROVIDERS.get(name)
    if provider is None:
        raise AiSuggestionError(f"unknown_provider:{name}")
    return provider


def _tenant_opt_in(organization_id: Optional[int]) -> bool:
    """Return True if the tenant has opted into AI suggestions."""
    if organization_id is None:
        return False
    # Honor a per-tenant toggle when the organization model has one;
    # until then, fall back to the app-level flag.
    from app.models.organization import Organization

    org = db.session.get(Organization, organization_id)
    per_tenant = getattr(org, "ai_suggestions_enabled", None)
    if per_tenant is not None:
        return bool(per_tenant)
    return bool(current_app.config.get("AI_SUGGESTIONS_ENABLED"))


def suggest(
    *,
    context: str,
    prompt: str,
    organization_id: int,
    user_id: int,
) -> list[Suggestion]:
    """Public entry point used by the HTTP layer and the orchestrator.

    Audits every call as a ``SecurityEvent`` so operators can review
    what left the tenant boundary.
    """
    if not isinstance(context, str) or len(context) > 20_000:
        raise AiSuggestionError("context_invalid")
    if not isinstance(prompt, str) or not 1 <= len(prompt) <= 2_000:
        raise AiSuggestionError("prompt_invalid")
    if not _tenant_opt_in(organization_id):
        raise AiSuggestionError("ai_suggestions_disabled_for_tenant")
    provider = active_provider()
    db.session.add(
        SecurityEvent(
            organization_id=organization_id,
            actor_id=user_id,
            action="ai.suggestion.requested",
            resource_type="ai_provider",
            resource_id=user_id,
            outcome="ok",
            correlation_id=uuid.uuid4().hex,
        )
    )
    try:
        suggestions = provider.suggest(
            context=context,
            prompt=prompt,
            organization_id=organization_id,
            user_id=user_id,
        )
    except Exception as exc:
        db.session.add(
            SecurityEvent(
                organization_id=organization_id,
                actor_id=user_id,
                action="ai.suggestion.provider_error",
                resource_type="ai_provider",
                resource_id=user_id,
                outcome="error",
                correlation_id=uuid.uuid4().hex,
            )
        )
        raise AiSuggestionError("provider_error") from exc
    return suggestions
