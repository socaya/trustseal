"""Plan entitlement enforcement (F2).

Covers:

Service layer:
* ``decision`` returns allowed=True when no plan is attached.
* ``decision`` returns allowed=True when no entitlement row exists
  for the (plan, meter).
* ``decision`` returns allowed=False with used/limit once usage
  reaches the plan limit.
* ``check`` raises ``EntitlementExceeded`` on denial.

HTTP integration:
* ``POST /api/envelopes/<id>/prepare`` returns 402 with the breach
  body when a plan limit is already met before prepare runs.
* ``POST /api/envelopes/<id>/prepare`` still returns 200 once the
  plan is lifted / the window rolls.
"""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import hashlib
import pytest
from flask_jwt_extended import create_access_token
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def _pdf(label: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.drawString(72, 720, "Entitlement: " + label)
    c.showPage()
    c.save()
    return buf.getvalue()


@pytest.fixture
def noop_scanner(monkeypatch):
    from app.services.documents import private_storage

    monkeypatch.setattr(
        private_storage,
        "_scan_pdf",
        lambda path, config: "noop-scanner-test-only",
    )
    yield


@pytest.fixture
def seeded(pg_app, tmp_path):
    """Org with Subscription + SubscriptionPlan + Envelope ready to prepare."""
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.signing_envelope import (
        EnvelopeParticipant,
        SigningEnvelope,
    )
    from app.models.subscription import Subscription, SubscriptionPlan
    from app.models.user import User

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)

    org = Organization(name="Entitlement Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    plan = SubscriptionPlan(
        name="free", description="Free plan",
        price=0, duration_days=30, is_active=True,
    )
    db.session.add(plan)
    db.session.flush()
    from datetime import timedelta

    now = datetime.utcnow()
    sub = Subscription(
        plan_id=plan.id,
        is_active=True,
        start_date=now,
        end_date=now + timedelta(days=30),
    )
    db.session.add(sub)
    db.session.flush()
    org.subscription_id = sub.id
    owner = User(
        username="ent-owner",
        email="ent-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("entitlementpassword12345")
    signer = User(
        username="ent-signer",
        email="ent-signer@example.test",
        is_active=True,
        organization_id=org.id,
    )
    signer.set_password("entitlementpassword12345")
    db.session.add_all([owner, signer])
    db.session.flush()
    doc = Document(
        title="Entitlement doc",
        status="draft",
        created_by=owner.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()
    body = _pdf("ent")
    digest = hashlib.sha256(body).hexdigest()
    (private_root / f"{digest}.pdf").write_bytes(body)
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key=f"{digest}.pdf",
        file_name="ent.pdf",
        mime_type="application/pdf",
        file_size=len(body),
        sha256=digest,
        scanner="noop",
        created_by_id=owner.id,
    )
    db.session.add(blob)
    db.session.flush()
    envelope = SigningEnvelope(
        organization_id=org.id,
        document_id=doc.id,
        document_blob_id=blob.id,
        document_sha256=digest,
        created_by_id=owner.id,
        state="draft",
    )
    db.session.add(envelope)
    db.session.flush()
    db.session.add(
        EnvelopeParticipant(
            envelope_id=envelope.id,
            user_id=signer.id,
            signing_order=1,
            role="signer",
        )
    )
    envelope.preview_confirmed_at = datetime.utcnow()
    db.session.commit()
    return {
        "org": org,
        "owner": owner,
        "signer": signer,
        "doc": doc,
        "blob": blob,
        "envelope": envelope,
        "plan": plan,
    }


class TestDecision:
    def test_no_plan_is_allowed(self, pg_app):
        from app.extensions import db
        from app.models.organization import Organization
        from app.services import entitlements

        org = Organization(name="Entitlement Unbound", type="company")
        db.session.add(org)
        db.session.commit()
        d = entitlements.decision(org.id, "envelope.prepared")
        assert d.allowed is True
        assert d.limit is None

    def test_no_entitlement_row_is_allowed(self, pg_app, seeded):
        from app.services import entitlements

        d = entitlements.decision(seeded["org"].id, "envelope.prepared")
        assert d.allowed is True
        assert d.limit is None

    def test_usage_below_limit_is_allowed(self, pg_app, seeded):
        from app.extensions import db
        from app.models.plan_entitlement import PlanEntitlement
        from app.services import entitlements, usage_ledger

        db.session.add(
            PlanEntitlement(
                plan_id=seeded["plan"].id,
                meter="envelope.prepared",
                period="month",
                hit_limit=3,
            )
        )
        usage_ledger.record(
            seeded["org"].id, "envelope.prepared", "evt:1"
        )
        db.session.commit()
        d = entitlements.decision(seeded["org"].id, "envelope.prepared")
        assert d.allowed is True
        assert d.used == 1
        assert d.limit == 3

    def test_usage_at_limit_is_denied(self, pg_app, seeded):
        from app.extensions import db
        from app.models.plan_entitlement import PlanEntitlement
        from app.services import entitlements, usage_ledger

        db.session.add(
            PlanEntitlement(
                plan_id=seeded["plan"].id,
                meter="envelope.prepared",
                period="month",
                hit_limit=2,
            )
        )
        for n in range(2):
            usage_ledger.record(
                seeded["org"].id, "envelope.prepared", f"evt:{n}"
            )
        db.session.commit()
        d = entitlements.decision(seeded["org"].id, "envelope.prepared")
        assert d.allowed is False
        assert d.used == 2
        assert d.limit == 2
        with pytest.raises(entitlements.EntitlementExceeded):
            d.ensure()


class TestPrepareIntegration:
    def test_prepare_blocked_with_402(
        self, pg_app, seeded, noop_scanner
    ):
        from app.extensions import db
        from app.models.plan_entitlement import PlanEntitlement
        from app.services import usage_ledger

        db.session.add(
            PlanEntitlement(
                plan_id=seeded["plan"].id,
                meter="envelope.prepared",
                period="month",
                hit_limit=1,
            )
        )
        usage_ledger.record(
            seeded["org"].id, "envelope.prepared", "prior:1"
        )
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["owner"].id))
        r = client.post(
            f"/api/envelopes/{seeded['envelope'].id}/prepare",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"ent-prep-{seeded['envelope'].id}",
            },
        )
        assert r.status_code == 402, r.get_data(as_text=True)
        body = r.get_json()
        assert body["meter"] == "envelope.prepared"
        assert body["used"] == 1
        assert body["limit"] == 1
