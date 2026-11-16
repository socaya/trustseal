"""Phase X — notification auto-emits + bulk envelope labeling."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token


# ============================================================ X1 notifications


class TestWebhookDeadNotification:
    def test_dead_delivery_emits_notification(self, pg_app):
        from app.extensions import db
        from app.models.operator_notification import OperatorNotification
        from app.models.organization import Organization
        from app.models.user import User
        from app.models.webhook import WebhookDelivery
        from app.services import webhooks

        org = Organization(name="X1 Tenant", type="company")
        db.session.add(org)
        db.session.flush()
        owner = User(
            username="x-webhook-owner",
            email="x-webhook-owner@example.test",
            is_active=True,
            organization_id=org.id,
        )
        owner.set_password("phase-x-password-123")
        db.session.add(owner)
        db.session.flush()
        endpoint, secret = webhooks.register_endpoint(
            tenant_id=org.id,
            created_by_id=owner.id,
            url="https://example.test/x-hook",
            events=["*"],
        )
        db.session.commit()
        deliveries = webhooks.fan_out_event(
            tenant_id=org.id,
            event_id="x-evt-dead",
            event_type="envelope.prepared",
            payload={"envelope_id": 7},
        )
        db.session.commit()
        delivery = deliveries[0]

        def failing_transport(url, data, headers, timeout):
            from app.services.webhooks import HttpResponse

            class _Resp:
                status_code = 500
                text = "boom"

            return _Resp()

        # Simulate repeated failures until it dies.
        for _ in range(webhooks.MAX_RETRIES):
            delivery.next_retry_at = datetime.utcnow() - timedelta(minutes=1)
            db.session.commit()
            webhooks.dispatch_due(
                transport=failing_transport,
                secret_resolver=lambda _ep: secret,
                limit=10,
            )
        db.session.expire_all()
        refreshed = db.session.get(WebhookDelivery, delivery.id)
        assert refreshed.status == "dead"
        notes = OperatorNotification.query.filter_by(
            recipient_user_id=owner.id,
            kind="webhook.delivery.dead",
        ).all()
        assert len(notes) >= 1
        assert notes[0].subject_id == delivery.id


# ============================================================ X2 bulk label


@pytest.fixture
def x2_seed(pg_app, tmp_path):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.signing_envelope import SigningEnvelope
    from app.models.user import User

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)

    org = Organization(name="X2 Tenant", type="company")
    other_org = Organization(name="X2 Other Tenant", type="company")
    db.session.add_all([org, other_org])
    db.session.flush()
    owner = User(
        username="x2-owner",
        email="x2-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-x-password-123")
    db.session.add(owner)
    db.session.flush()

    envelopes = []
    for n in range(3):
        doc = Document(
            title=f"X2 doc {n}",
            status="draft",
            created_by=owner.id,
            organization_id=org.id,
        )
        db.session.add(doc)
        db.session.flush()
        body = f"%PDF-1.4\n% x2-{n}\n%%EOF".encode()
        digest = hashlib.sha256(body).hexdigest()
        (private_root / f"{digest}.pdf").write_bytes(body)
        blob = DocumentBlob(
            document_id=doc.id,
            revision=1,
            object_key=f"{digest}.pdf",
            file_name=f"x2-{n}.pdf",
            mime_type="application/pdf",
            file_size=len(body),
            sha256=digest,
            scanner="noop",
            created_by_id=owner.id,
        )
        db.session.add(blob)
        db.session.flush()
        env = SigningEnvelope(
            organization_id=org.id,
            document_id=doc.id,
            document_blob_id=blob.id,
            document_sha256=digest,
            created_by_id=owner.id,
            state="prepared",
            prepared_at=datetime.utcnow(),
        )
        db.session.add(env)
        db.session.flush()
        envelopes.append(env)
    db.session.commit()
    return {"org": org, "other_org": other_org, "owner": owner, "envelopes": envelopes}


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}


class TestBulkLabel:
    def test_all_rows_tagged(self, pg_app, x2_seed):
        from app.extensions import db
        from app.models.signing_envelope import EnvelopeLabel

        client = pg_app.test_client()
        ids = [e.id for e in x2_seed["envelopes"]]
        r = client.post(
            "/api/envelopes/bulk/label",
            json={"envelope_ids": ids, "label": "quarterly"},
            headers=_auth(x2_seed["owner"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["succeeded"] == 3
        assert body["added"] == 3
        db.session.expire_all()
        count = EnvelopeLabel.query.filter_by(label="quarterly").count()
        assert count == 3

    def test_existing_tag_idempotent(self, pg_app, x2_seed):
        from app.extensions import db
        from app.models.signing_envelope import EnvelopeLabel

        client = pg_app.test_client()
        # Pre-tag one envelope.
        db.session.add(
            EnvelopeLabel(
                envelope_id=x2_seed["envelopes"][0].id,
                organization_id=x2_seed["org"].id,
                label="hr",
                created_by_id=x2_seed["owner"].id,
            )
        )
        db.session.commit()
        ids = [e.id for e in x2_seed["envelopes"]]
        r = client.post(
            "/api/envelopes/bulk/label",
            json={"envelope_ids": ids, "label": "hr"},
            headers=_auth(x2_seed["owner"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        # 3 succeeded total but added only 2 — the first was already tagged.
        assert body["added"] == 2
        assert body["succeeded"] == 3
        already = [row for row in body["results"] if row.get("already_tagged")]
        assert len(already) == 1

    def test_mixed_batch_207(self, pg_app, x2_seed):
        client = pg_app.test_client()
        ids = [e.id for e in x2_seed["envelopes"]] + [99999999]
        r = client.post(
            "/api/envelopes/bulk/label",
            json={"envelope_ids": ids, "label": "finance"},
            headers=_auth(x2_seed["owner"]),
        )
        assert r.status_code == 207
        body = r.get_json()
        assert body["succeeded"] == 3
        assert body["failed"] == 1
        failure = next(r for r in body["results"] if r["status"] == "failed")
        assert failure["error_code"] == "envelope_not_found"

    def test_all_fail_rolls_back(self, pg_app, x2_seed):
        from app.extensions import db
        from app.models.signing_envelope import EnvelopeLabel

        client = pg_app.test_client()
        r = client.post(
            "/api/envelopes/bulk/label",
            json={"envelope_ids": [99999999], "label": "finance"},
            headers=_auth(x2_seed["owner"]),
        )
        assert r.status_code == 400
        db.session.expire_all()
        count = EnvelopeLabel.query.filter_by(label="finance").count()
        assert count == 0

    def test_limit_100(self, pg_app, x2_seed):
        client = pg_app.test_client()
        r = client.post(
            "/api/envelopes/bulk/label",
            json={"envelope_ids": list(range(1, 102)), "label": "finance"},
            headers=_auth(x2_seed["owner"]),
        )
        assert r.status_code == 413

    def test_bad_label_rejected(self, pg_app, x2_seed):
        client = pg_app.test_client()
        r = client.post(
            "/api/envelopes/bulk/label",
            json={
                "envelope_ids": [x2_seed["envelopes"][0].id],
                "label": "has space",
            },
            headers=_auth(x2_seed["owner"]),
        )
        assert r.status_code == 400
