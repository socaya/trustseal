"""Conditional routing rules (H1).

Predicate evaluator tests + integration into the signer-intent
eligibility gate.
"""
from __future__ import annotations

import hashlib
import io
from datetime import datetime
from pathlib import Path

import pytest
from flask_jwt_extended import create_access_token


# ============================================================ evaluator


class TestEvaluator:
    def test_eq_resolves_ref_and_literal(self):
        from app.services.envelope_routing_rules import evaluate_predicate

        ctx = {"participant": {"role": "witness"}}
        assert evaluate_predicate(
            {"op": "eq", "lhs": {"ref": "participant.role"}, "rhs": "witness"},
            ctx,
        ) is True
        assert evaluate_predicate(
            {"op": "eq", "lhs": {"ref": "participant.role"}, "rhs": "signer"},
            ctx,
        ) is False

    def test_ge_lt(self):
        from app.services.envelope_routing_rules import evaluate_predicate

        ctx = {"prior_decisions": {"acknowledged_count": 3}}
        assert evaluate_predicate(
            {
                "op": "ge",
                "lhs": {"ref": "prior_decisions.acknowledged_count"},
                "rhs": 2,
            },
            ctx,
        ) is True
        assert evaluate_predicate(
            {
                "op": "lt",
                "lhs": {"ref": "prior_decisions.acknowledged_count"},
                "rhs": 2,
            },
            ctx,
        ) is False

    def test_and_or_not(self):
        from app.services.envelope_routing_rules import evaluate_predicate

        ctx = {"participant": {"role": "witness"}, "n": 3}
        assert evaluate_predicate(
            {
                "op": "and",
                "args": [
                    {
                        "op": "eq",
                        "lhs": {"ref": "participant.role"},
                        "rhs": "witness",
                    },
                    {"op": "ge", "lhs": {"ref": "n"}, "rhs": 2},
                ],
            },
            ctx,
        ) is True
        assert evaluate_predicate(
            {
                "op": "or",
                "args": [
                    {
                        "op": "eq",
                        "lhs": {"ref": "participant.role"},
                        "rhs": "signer",
                    },
                    {"op": "ge", "lhs": {"ref": "n"}, "rhs": 100},
                ],
            },
            ctx,
        ) is False
        assert evaluate_predicate(
            {
                "op": "not",
                "arg": {
                    "op": "eq",
                    "lhs": {"ref": "participant.role"},
                    "rhs": "signer",
                },
            },
            ctx,
        ) is True

    def test_unknown_ref_raises(self):
        from app.services.envelope_routing_rules import (
            RuleError,
            evaluate_predicate,
        )

        with pytest.raises(RuleError) as exc:
            evaluate_predicate(
                {"op": "eq", "lhs": {"ref": "nowhere"}, "rhs": 1},
                {},
            )
        assert "ref_unknown" in str(exc.value)

    def test_unknown_op_raises(self):
        from app.services.envelope_routing_rules import (
            RuleError,
            evaluate_predicate,
        )

        with pytest.raises(RuleError) as exc:
            evaluate_predicate({"op": "contains", "lhs": "a", "rhs": "a"}, {})
        assert "op_unknown" in str(exc.value)


# ============================================================ integration


@pytest.fixture
def seeded(pg_app, tmp_path):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.signing_envelope import (
        EnvelopeParticipant,
        SigningEnvelope,
    )
    from app.models.user import User

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)

    org = Organization(name="Rules Tenant", type="company")
    db.session.add(org)
    db.session.flush()

    def mk(name, email):
        u = User(
            username=name,
            email=email,
            is_active=True,
            organization_id=org.id,
        )
        u.set_password("rulespassword12345")
        db.session.add(u)
        db.session.flush()
        return u

    creator = mk("rules-creator", "rules-creator@example.test")
    signer_a = mk("rules-signer-a", "rules-signer-a@example.test")
    signer_b = mk("rules-signer-b", "rules-signer-b@example.test")
    witness = mk("rules-witness", "rules-witness@example.test")

    doc = Document(
        title="Rules doc",
        status="draft",
        created_by=creator.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()
    body = b"%PDF-1.4\n% rules\n%%EOF"
    digest = hashlib.sha256(body).hexdigest()
    (Path(private_root) / f"{digest}.pdf").write_bytes(body)
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key=f"{digest}.pdf",
        file_name="rules.pdf",
        mime_type="application/pdf",
        file_size=len(body),
        sha256=digest,
        scanner="noop",
        created_by_id=creator.id,
    )
    db.session.add(blob)
    db.session.flush()
    envelope = SigningEnvelope(
        organization_id=org.id,
        document_id=doc.id,
        document_blob_id=blob.id,
        document_sha256=digest,
        created_by_id=creator.id,
        state="draft",
        routing_mode="parallel",
    )
    db.session.add(envelope)
    db.session.flush()
    p_a = EnvelopeParticipant(
        envelope_id=envelope.id,
        user_id=signer_a.id,
        signing_order=1,
        role="signer",
    )
    p_b = EnvelopeParticipant(
        envelope_id=envelope.id,
        user_id=signer_b.id,
        signing_order=2,
        role="signer",
    )
    p_w = EnvelopeParticipant(
        envelope_id=envelope.id,
        user_id=witness.id,
        signing_order=3,
        role="witness",
    )
    db.session.add_all([p_a, p_b, p_w])
    db.session.commit()
    return {
        "org": org,
        "creator": creator,
        "signer_a": signer_a,
        "signer_b": signer_b,
        "witness": witness,
        "envelope": envelope,
        "p_a": p_a,
        "p_b": p_b,
        "p_w": p_w,
    }


class TestServiceCRUD:
    def test_add_rule_requires_draft(self, pg_app, seeded):
        from app.extensions import db
        from app.services import envelope_routing_rules

        seeded["envelope"].state = "prepared"
        db.session.commit()
        with pytest.raises(envelope_routing_rules.RuleError) as exc:
            envelope_routing_rules.add_rule(
                seeded["envelope"],
                seeded["p_a"],
                name="r1",
                predicate={"op": "eq", "lhs": 1, "rhs": 1},
                created_by_id=seeded["creator"].id,
            )
        assert "not_draft" in str(exc.value)

    def test_add_list_delete_rule(self, pg_app, seeded):
        from app.extensions import db
        from app.services import envelope_routing_rules

        rule = envelope_routing_rules.add_rule(
            seeded["envelope"],
            seeded["p_a"],
            name="requires-acknowledged",
            predicate={
                "op": "ge",
                "lhs": {"ref": "prior_decisions.acknowledged_count"},
                "rhs": 1,
            },
            created_by_id=seeded["creator"].id,
        )
        db.session.commit()
        rules = envelope_routing_rules.list_rules(seeded["envelope"])
        assert [r.id for r in rules] == [rule.id]
        envelope_routing_rules.delete_rule(seeded["envelope"], rule.id)
        db.session.commit()
        assert envelope_routing_rules.list_rules(seeded["envelope"]) == []


class TestIntegration:
    def test_rule_blocks_until_prior_acknowledged(self, pg_app, seeded):
        """Signer B requires signer A's acknowledgement."""
        from app.extensions import db
        from app.services import envelope_routing_rules

        envelope_routing_rules.add_rule(
            seeded["envelope"],
            seeded["p_b"],
            name="after-a",
            predicate={
                "op": "ge",
                "lhs": {"ref": "prior_decisions.acknowledged_count"},
                "rhs": 1,
            },
            created_by_id=seeded["creator"].id,
        )
        seeded["envelope"].state = "prepared"
        seeded["envelope"].prepared_at = datetime.utcnow()
        db.session.commit()
        client = pg_app.test_client()
        # Signer B tries first — blocked by the rule.
        token_b = create_access_token(identity=str(seeded["signer_b"].id))
        r = client.post(
            f"/api/signer-intent/envelopes/{seeded['envelope'].id}/challenge",
            json={"password": "rulespassword12345"},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert r.status_code == 409
        assert "routing_rule_blocked" in r.get_data(as_text=True)
        # Signer A goes first (parallel mode allows any order).
        token_a = create_access_token(identity=str(seeded["signer_a"].id))
        r = client.post(
            f"/api/signer-intent/envelopes/{seeded['envelope'].id}/challenge",
            json={"password": "rulespassword12345"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert r.status_code == 201
        body = r.get_json()
        r = client.post(
            f"/api/signer-intent/envelopes/{seeded['envelope'].id}/decision",
            json={
                "challenge_id": body["challenge_id"],
                "challenge": body["challenge"],
                "decision": "acknowledged",
                "document_sha256": seeded["envelope"].document_sha256,
                "consent_version": "review-intent-v1",
                "affirmed": True,
            },
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert r.status_code == 201
        # Now signer B is unblocked.
        r = client.post(
            f"/api/signer-intent/envelopes/{seeded['envelope'].id}/challenge",
            json={"password": "rulespassword12345"},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert r.status_code == 201

    def test_api_add_rule_as_creator(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["creator"].id))
        r = client.post(
            f"/api/envelopes/{seeded['envelope'].id}/"
            f"participants/{seeded['p_b'].id}/rules",
            json={
                "name": "after-a",
                "predicate": {
                    "op": "ge",
                    "lhs": {
                        "ref": "prior_decisions.acknowledged_count"
                    },
                    "rhs": 1,
                },
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201, r.get_data(as_text=True)
        body = r.get_json()
        assert body["participant_id"] == seeded["p_b"].id
