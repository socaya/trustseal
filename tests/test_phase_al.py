"""Phase AL — bulk reminder cadence + audit anchor listing."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from flask_jwt_extended import create_access_token


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}


# ============================================================ AL1 bulk cadence


@pytest.fixture
def al1_seed(pg_app, tmp_path):
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.documents.document_blob import DocumentBlob
    from app.models.organization import Organization
    from app.models.signing_envelope import SigningEnvelope
    from app.models.user import User

    private_root = tmp_path / "private"
    private_root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(private_root)
    org = Organization(name="AL1 Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    owner = User(
        username="al1-owner",
        email="al1-owner@example.test",
        is_active=True,
        organization_id=org.id,
    )
    owner.set_password("phase-al-password-123")
    db.session.add(owner)
    db.session.flush()
    envelopes = []
    for n in range(3):
        doc = Document(
            title=f"AL1 doc {n}",
            status="draft",
            created_by=owner.id,
            organization_id=org.id,
        )
        db.session.add(doc)
        db.session.flush()
        body = f"%PDF-1.4\n% al1-{n}\n%%EOF".encode()
        digest = hashlib.sha256(body).hexdigest()
        (private_root / f"{digest}.pdf").write_bytes(body)
        blob = DocumentBlob(
            document_id=doc.id,
            revision=1,
            object_key=f"{digest}.pdf",
            file_name=f"al1-{n}.pdf",
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
            state="draft",
        )
        db.session.add(env)
        db.session.flush()
        envelopes.append(env)
    db.session.commit()
    return {"org": org, "owner": owner, "envelopes": envelopes}


class TestBulkCadence:
    def test_applies_cooloff_and_max(self, pg_app, al1_seed):
        from app.extensions import db
        from app.models.signing_envelope import SigningEnvelope

        client = pg_app.test_client()
        ids = [e.id for e in al1_seed["envelopes"]]
        r = client.post(
            "/api/envelopes/bulk/reminders",
            json={"envelope_ids": ids, "cooloff_hours": 6, "max_count": 2},
            headers=_auth(al1_seed["owner"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["updated"] == 3
        db.session.expire_all()
        for env_id in ids:
            refreshed = db.session.get(SigningEnvelope, env_id)
            assert refreshed.reminder_cooloff_hours == 6
            assert refreshed.reminder_max_count == 2

    def test_null_clears_override(self, pg_app, al1_seed):
        from app.extensions import db
        from app.models.signing_envelope import SigningEnvelope

        for env in al1_seed["envelopes"]:
            env.reminder_cooloff_hours = 12
            env.reminder_max_count = 5
        db.session.commit()
        client = pg_app.test_client()
        r = client.post(
            "/api/envelopes/bulk/reminders",
            json={
                "envelope_ids": [e.id for e in al1_seed["envelopes"]],
                "cooloff_hours": None,
            },
            headers=_auth(al1_seed["owner"]),
        )
        assert r.status_code == 200
        db.session.expire_all()
        for env in al1_seed["envelopes"]:
            refreshed = db.session.get(SigningEnvelope, env.id)
            assert refreshed.reminder_cooloff_hours is None
            # max_count unchanged (field not in payload).
            assert refreshed.reminder_max_count == 5

    def test_range_validation(self, pg_app, al1_seed):
        client = pg_app.test_client()
        ids = [al1_seed["envelopes"][0].id]
        for bad in (
            {"cooloff_hours": 0},
            {"cooloff_hours": 10_000},
            {"max_count": 0},
            {"max_count": 51},
        ):
            r = client.post(
                "/api/envelopes/bulk/reminders",
                json={"envelope_ids": ids, **bad},
                headers=_auth(al1_seed["owner"]),
            )
            assert r.status_code == 400, bad

    def test_missing_fields_rejected(self, pg_app, al1_seed):
        client = pg_app.test_client()
        r = client.post(
            "/api/envelopes/bulk/reminders",
            json={"envelope_ids": [al1_seed["envelopes"][0].id]},
            headers=_auth(al1_seed["owner"]),
        )
        assert r.status_code == 400

    def test_mixed_batch_207(self, pg_app, al1_seed):
        client = pg_app.test_client()
        ids = [e.id for e in al1_seed["envelopes"]] + [9999999]
        r = client.post(
            "/api/envelopes/bulk/reminders",
            json={"envelope_ids": ids, "cooloff_hours": 3},
            headers=_auth(al1_seed["owner"]),
        )
        assert r.status_code == 207
        body = r.get_json()
        assert body["succeeded"] == 3
        assert body["failed"] == 1

    def test_limit_100(self, pg_app, al1_seed):
        client = pg_app.test_client()
        r = client.post(
            "/api/envelopes/bulk/reminders",
            json={"envelope_ids": list(range(1, 102)), "cooloff_hours": 6},
            headers=_auth(al1_seed["owner"]),
        )
        assert r.status_code == 413


# ============================================================ AL2 anchor listing


@pytest.fixture
def al2_seed(pg_app):
    from app.extensions import db
    from app.models.audit_chain_anchor import AuditChainAnchor
    from app.models.organization import Organization
    from app.models.system import Role, UserRole
    from app.models.user import User

    org = Organization(name="AL2 Tenant", type="company")
    other_org = Organization(name="AL2 Other", type="company")
    db.session.add_all([org, other_org])
    db.session.flush()
    role = Role.query.filter_by(name="admin").one_or_none() or Role(
        name="admin", description="test"
    )
    db.session.add(role)
    db.session.flush()
    admin = User(
        username="al2-admin",
        email="al2-admin@example.test",
        is_active=True,
        organization_id=org.id,
    )
    admin.set_password("phase-al-password-123")
    regular = User(
        username="al2-regular",
        email="al2-regular@example.test",
        is_active=True,
        organization_id=org.id,
    )
    regular.set_password("phase-al-password-123")
    db.session.add_all([admin, regular])
    db.session.flush()
    db.session.add(UserRole(user_id=admin.id, role_id=role.id))
    key = Ed25519PrivateKey.generate()
    key_id = hashlib.sha256(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).hexdigest()[:40]
    anchors = []
    for n in range(3):
        payload = {"organization_id": org.id, "anchor_event_id": 100 + n}
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        signature = key.sign(canonical).hex()
        anchor = AuditChainAnchor(
            organization_id=org.id,
            anchor_event_id=100 + n,
            chain_tip_hash=hashlib.sha256(f"tip{n}".encode()).hexdigest(),
            payload=payload,
            algorithm="ed25519",
            key_id=key_id,
            signature=signature,
            operator_id=admin.id,
        )
        db.session.add(anchor)
        db.session.flush()
        anchors.append(anchor)
    # Cross-tenant noise.
    cross_payload = {"organization_id": other_org.id, "anchor_event_id": 999}
    cross_canonical = json.dumps(
        cross_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    db.session.add(
        AuditChainAnchor(
            organization_id=other_org.id,
            anchor_event_id=999,
            chain_tip_hash=hashlib.sha256(b"cross").hexdigest(),
            payload=cross_payload,
            algorithm="ed25519",
            key_id=key_id,
            signature=key.sign(cross_canonical).hex(),
            operator_id=admin.id,
        )
    )
    db.session.commit()
    return {
        "org": org,
        "admin": admin,
        "regular": regular,
        "anchors": anchors,
    }


class TestAnchorListing:
    def test_lists_tenant_anchors(self, pg_app, al2_seed):
        client = pg_app.test_client()
        r = client.get(
            "/api/_internal/audit/anchors",
            headers=_auth(al2_seed["admin"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["count"] == 3
        event_ids = {row["anchor_event_id"] for row in body["anchors"]}
        assert event_ids == {100, 101, 102}

    def test_after_id_pagination(self, pg_app, al2_seed):
        client = pg_app.test_client()
        first_id = al2_seed["anchors"][0].id
        r = client.get(
            f"/api/_internal/audit/anchors?after_id={first_id}",
            headers=_auth(al2_seed["admin"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["count"] == 2
        assert all(row["id"] > first_id for row in body["anchors"])

    def test_requires_admin(self, pg_app, al2_seed):
        client = pg_app.test_client()
        r = client.get(
            "/api/_internal/audit/anchors",
            headers=_auth(al2_seed["regular"]),
        )
        assert r.status_code == 403

    def test_limit_out_of_range(self, pg_app, al2_seed):
        client = pg_app.test_client()
        r = client.get(
            "/api/_internal/audit/anchors?limit=9999",
            headers=_auth(al2_seed["admin"]),
        )
        assert r.status_code == 400
