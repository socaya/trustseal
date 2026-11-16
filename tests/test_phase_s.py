"""Phase S — envelope templates + X-Trace/Request-Id headers."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

import pytest
from flask_jwt_extended import create_access_token


@pytest.fixture
def phase_s_seed(pg_app, tmp_path):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.user import User

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)

    org = Organization(name="S Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    owner = User(
        username="s-owner",
        email="s-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-s-password-123")
    db.session.add(owner)
    db.session.flush()

    signers = []
    for n in range(3):
        u = User(
            username=f"s-signer-{n}",
            email=f"s-signer-{n}@example.test",
            is_active=True,
            organization_id=org.id,
        )
        u.set_password("phase-s-password-123")
        db.session.add(u)
        db.session.flush()
        signers.append(u)

    doc = Document(
        title="S doc",
        status="draft",
        created_by=owner.id,
        organization_id=org.id,
    )
    db.session.add(doc)
    db.session.flush()
    body = b"%PDF-1.4\n% s\n%%EOF"
    digest = hashlib.sha256(body).hexdigest()
    (private_root / f"{digest}.pdf").write_bytes(body)
    blob = DocumentBlob(
        document_id=doc.id,
        revision=1,
        object_key=f"{digest}.pdf",
        file_name="s.pdf",
        mime_type="application/pdf",
        file_size=len(body),
        sha256=digest,
        scanner="noop",
        created_by_id=owner.id,
    )
    db.session.add(blob)
    db.session.commit()
    return {
        "org": org,
        "owner": owner,
        "signers": signers,
        "document": doc,
        "blob": blob,
    }


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}


# ============================================================ S1 templates


class TestEnvelopeTemplateCRUD:
    def test_create_list_get(self, pg_app, phase_s_seed):
        client = pg_app.test_client()
        user = phase_s_seed["owner"]
        r = client.post(
            "/api/envelope-templates",
            json={
                "name": "Quarterly audit",
                "routing_mode": "sequential",
                "reminder_cooloff_hours": 12,
                "reminder_max_count": 4,
                "expires_in_hours": 72,
            },
            headers=_auth(user),
        )
        assert r.status_code == 201, r.get_data(as_text=True)
        tid = r.get_json()["id"]
        listing = client.get("/api/envelope-templates", headers=_auth(user))
        assert listing.status_code == 200
        ids = {row["id"] for row in listing.get_json()}
        assert tid in ids
        detail = client.get(
            f"/api/envelope-templates/{tid}", headers=_auth(user)
        )
        assert detail.status_code == 200
        body = detail.get_json()
        assert body["name"] == "Quarterly audit"
        assert body["expires_in_hours"] == 72

    def test_name_unique_per_org(self, pg_app, phase_s_seed):
        client = pg_app.test_client()
        user = phase_s_seed["owner"]
        client.post(
            "/api/envelope-templates",
            json={"name": "DupeName"},
            headers=_auth(user),
        )
        second = client.post(
            "/api/envelope-templates",
            json={"name": "DupeName"},
            headers=_auth(user),
        )
        assert second.status_code == 409

    def test_quorum_validation(self, pg_app, phase_s_seed):
        client = pg_app.test_client()
        user = phase_s_seed["owner"]
        r = client.post(
            "/api/envelope-templates",
            json={"name": "Bad quorum", "routing_mode": "quorum"},
            headers=_auth(user),
        )
        assert r.status_code == 400

    def test_patch_name_and_cadence(self, pg_app, phase_s_seed):
        client = pg_app.test_client()
        user = phase_s_seed["owner"]
        created = client.post(
            "/api/envelope-templates",
            json={"name": "To Edit"},
            headers=_auth(user),
        ).get_json()
        tid = created["id"]
        r = client.patch(
            f"/api/envelope-templates/{tid}",
            json={
                "name": "Renamed",
                "reminder_cooloff_hours": 6,
                "reminder_max_count": 2,
            },
            headers=_auth(user),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["name"] == "Renamed"
        assert body["reminder_cooloff_hours"] == 6
        assert body["reminder_max_count"] == 2

    def test_delete_cascades_participants(self, pg_app, phase_s_seed):
        from app.extensions import db
        from app.models.envelope_template import (
            EnvelopeTemplateParticipant,
        )

        client = pg_app.test_client()
        user = phase_s_seed["owner"]
        created = client.post(
            "/api/envelope-templates",
            json={"name": "To Drop"},
            headers=_auth(user),
        ).get_json()
        tid = created["id"]
        client.post(
            f"/api/envelope-templates/{tid}/participants",
            json={
                "user_id": phase_s_seed["signers"][0].id,
                "signing_order": 1,
            },
            headers=_auth(user),
        )
        r = client.delete(
            f"/api/envelope-templates/{tid}", headers=_auth(user)
        )
        assert r.status_code == 200
        db.session.expire_all()
        remaining = EnvelopeTemplateParticipant.query.filter_by(
            template_id=tid
        ).count()
        assert remaining == 0


class TestEnvelopeTemplateParticipants:
    def test_add_and_remove(self, pg_app, phase_s_seed):
        client = pg_app.test_client()
        user = phase_s_seed["owner"]
        created = client.post(
            "/api/envelope-templates",
            json={"name": "Roster"},
            headers=_auth(user),
        ).get_json()
        tid = created["id"]
        add = client.post(
            f"/api/envelope-templates/{tid}/participants",
            json={
                "user_id": phase_s_seed["signers"][0].id,
                "signing_order": 1,
            },
            headers=_auth(user),
        )
        assert add.status_code == 201
        pid = add.get_json()["id"]
        r = client.delete(
            f"/api/envelope-templates/{tid}/participants/{pid}",
            headers=_auth(user),
        )
        assert r.status_code == 200

    def test_duplicate_user_rejected(self, pg_app, phase_s_seed):
        client = pg_app.test_client()
        user = phase_s_seed["owner"]
        created = client.post(
            "/api/envelope-templates",
            json={"name": "DupUser"},
            headers=_auth(user),
        ).get_json()
        tid = created["id"]
        client.post(
            f"/api/envelope-templates/{tid}/participants",
            json={
                "user_id": phase_s_seed["signers"][0].id,
                "signing_order": 1,
            },
            headers=_auth(user),
        )
        r = client.post(
            f"/api/envelope-templates/{tid}/participants",
            json={
                "user_id": phase_s_seed["signers"][0].id,
                "signing_order": 2,
            },
            headers=_auth(user),
        )
        assert r.status_code == 409


class TestEnvelopeTemplateInstantiate:
    def _make_template(self, client, phase_s_seed, name: str, signers):
        user = phase_s_seed["owner"]
        tpl = client.post(
            "/api/envelope-templates",
            json={
                "name": name,
                "routing_mode": "sequential",
                "reminder_cooloff_hours": 12,
                "reminder_max_count": 3,
                "expires_in_hours": 48,
            },
            headers=_auth(user),
        ).get_json()
        for idx, s in enumerate(signers):
            client.post(
                f"/api/envelope-templates/{tpl['id']}/participants",
                json={"user_id": s.id, "signing_order": idx + 1},
                headers=_auth(user),
            )
        return tpl

    def test_instantiate_creates_draft_envelope(
        self, pg_app, phase_s_seed
    ):
        from app.extensions import db
        from app.models.signing_envelope import (
            EnvelopeParticipant,
            SigningEnvelope,
        )

        client = pg_app.test_client()
        user = phase_s_seed["owner"]
        tpl = self._make_template(
            client, phase_s_seed, "InstTest", phase_s_seed["signers"][:2]
        )
        r = client.post(
            f"/api/envelope-templates/{tpl['id']}/instantiate",
            json={
                "document_id": phase_s_seed["document"].id,
                "document_blob_id": phase_s_seed["blob"].id,
            },
            headers=_auth(user),
        )
        assert r.status_code == 201, r.get_data(as_text=True)
        body = r.get_json()
        assert body["participants_created"] == 2
        env_id = body["envelope_id"]
        db.session.expire_all()
        env = db.session.get(SigningEnvelope, env_id)
        assert env.state == "draft"
        assert env.routing_mode == "sequential"
        assert env.reminder_cooloff_hours == 12
        assert env.reminder_max_count == 3
        assert env.expires_at is not None
        participants = EnvelopeParticipant.query.filter_by(
            envelope_id=env_id
        ).count()
        assert participants == 2

    def test_stale_recipient_blocks_instantiation(
        self, pg_app, phase_s_seed
    ):
        from app.extensions import db

        client = pg_app.test_client()
        user = phase_s_seed["owner"]
        tpl = self._make_template(
            client, phase_s_seed, "StaleTest", [phase_s_seed["signers"][0]]
        )
        # Deactivate the template's signer — the template should
        # refuse to instantiate instead of silently creating a draft
        # with a dead participant.
        phase_s_seed["signers"][0].is_active = False
        db.session.commit()
        r = client.post(
            f"/api/envelope-templates/{tpl['id']}/instantiate",
            json={
                "document_id": phase_s_seed["document"].id,
                "document_blob_id": phase_s_seed["blob"].id,
            },
            headers=_auth(user),
        )
        assert r.status_code == 409
        body = r.get_json()
        assert body["error"] == "stale_template_participants"


# ============================================================ S2 trace ID


class TestTraceAndRequestHeaders:
    def test_response_includes_request_and_trace_headers(
        self, pg_app, phase_s_seed
    ):
        client = pg_app.test_client()
        r = client.get(
            "/api/envelope-templates", headers=_auth(phase_s_seed["owner"])
        )
        assert r.status_code == 200
        assert "X-Request-Id" in r.headers
        assert "X-Trace-Id" in r.headers
        # UUID-like / non-empty
        assert len(r.headers["X-Request-Id"]) >= 16

    def test_incoming_request_id_is_echoed(self, pg_app, phase_s_seed):
        client = pg_app.test_client()
        rid = f"client-{uuid.uuid4().hex}"
        r = client.get(
            "/api/envelope-templates",
            headers={**_auth(phase_s_seed["owner"]), "X-Request-Id": rid},
        )
        assert r.headers["X-Request-Id"] == rid

    def test_bogus_incoming_request_id_is_replaced(
        self, pg_app, phase_s_seed
    ):
        client = pg_app.test_client()
        r = client.get(
            "/api/envelope-templates",
            headers={
                **_auth(phase_s_seed["owner"]),
                "X-Request-Id": "has space",
            },
        )
        # Replaced by a mint; must not contain whitespace.
        assert " " not in r.headers["X-Request-Id"]
