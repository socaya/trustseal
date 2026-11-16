"""AI suggestion provider abstraction (J2)."""
from __future__ import annotations

import pytest


@pytest.fixture
def seeded(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.user import User

    org = Organization(name="AI Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    user = User(
        username="ai-user",
        email="ai-user@example.test",
        is_active=True,
        organization_id=org.id,
    )
    user.set_password("aipassword12345")
    db.session.add(user)
    db.session.commit()
    pg_app.config["AI_SUGGESTIONS_ENABLED"] = False
    return {"org": org, "user": user}


class TestPolicy:
    def test_refuses_when_disabled(self, pg_app, seeded):
        from app.services import ai_suggestions

        with pytest.raises(ai_suggestions.AiSuggestionError) as exc:
            ai_suggestions.suggest(
                context="",
                prompt="rewrite",
                organization_id=seeded["org"].id,
                user_id=seeded["user"].id,
            )
        assert "disabled" in str(exc.value)

    def test_empty_prompt_rejected(self, pg_app, seeded):
        from app.services import ai_suggestions

        pg_app.config["AI_SUGGESTIONS_ENABLED"] = True
        with pytest.raises(ai_suggestions.AiSuggestionError):
            ai_suggestions.suggest(
                context="",
                prompt="",
                organization_id=seeded["org"].id,
                user_id=seeded["user"].id,
            )

    def test_oversized_context_rejected(self, pg_app, seeded):
        from app.services import ai_suggestions

        pg_app.config["AI_SUGGESTIONS_ENABLED"] = True
        with pytest.raises(ai_suggestions.AiSuggestionError):
            ai_suggestions.suggest(
                context="x" * 20_001,
                prompt="please",
                organization_id=seeded["org"].id,
                user_id=seeded["user"].id,
            )


class TestNoopProvider:
    def test_noop_returns_empty_list(self, pg_app, seeded):
        from app.services import ai_suggestions

        pg_app.config["AI_SUGGESTIONS_ENABLED"] = True
        out = ai_suggestions.suggest(
            context="hello",
            prompt="rewrite shorter",
            organization_id=seeded["org"].id,
            user_id=seeded["user"].id,
        )
        assert out == []

    def test_audit_event_emitted(self, pg_app, seeded):
        from app.extensions import db
        from app.models.event_delivery import SecurityEvent
        from app.services import ai_suggestions

        pg_app.config["AI_SUGGESTIONS_ENABLED"] = True
        ai_suggestions.suggest(
            context="hello",
            prompt="rewrite shorter",
            organization_id=seeded["org"].id,
            user_id=seeded["user"].id,
        )
        db.session.commit()
        count = SecurityEvent.query.filter_by(
            action="ai.suggestion.requested",
            organization_id=seeded["org"].id,
        ).count()
        assert count == 1


class TestRegistry:
    def test_register_and_use_provider(self, pg_app, seeded):
        from app.services import ai_suggestions

        class FakeProvider(ai_suggestions.AiSuggestionProvider):
            name = "fake-ai"

            def suggest(self, *, context, prompt, organization_id, user_id):
                return [
                    ai_suggestions.Suggestion(
                        text="fake-rewrite", confidence=0.95, rationale="probe"
                    )
                ]

        ai_suggestions.register_provider(FakeProvider())
        pg_app.config["AI_SUGGESTIONS_ENABLED"] = True
        pg_app.config["AI_SUGGESTION_PROVIDER"] = "fake-ai"
        try:
            out = ai_suggestions.suggest(
                context="hello",
                prompt="rewrite",
                organization_id=seeded["org"].id,
                user_id=seeded["user"].id,
            )
            assert len(out) == 1
            assert out[0].text == "fake-rewrite"
        finally:
            pg_app.config["AI_SUGGESTION_PROVIDER"] = "noop"
