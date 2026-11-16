"""Signed audit-chain slice export (M3)."""
from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from flask_jwt_extended import create_access_token


def _ed25519_pem_pair():
    key = ed25519.Ed25519PrivateKey.generate()
    priv = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return priv, pub


@pytest.fixture
def seeded(pg_app):
    """Admin + handful of SecurityEvent rows chained together."""
    import uuid

    from app.extensions import db
    from app.models.event_delivery import SecurityEvent
    from app.models.organization import Organization
    from app.models.system import Role, UserRole
    from app.models.user import User

    org = Organization(name="Audit Export Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    role = Role.query.filter_by(name="admin").one_or_none() or Role(
        name="admin", description="test"
    )
    db.session.add(role)
    db.session.flush()
    admin = User(
        username="audit-admin",
        email="audit-admin@example.test",
        is_active=True,
        organization_id=org.id,
    )
    admin.set_password("auditpassword12345")
    db.session.add(admin)
    db.session.flush()
    db.session.add(UserRole(user_id=admin.id, role_id=role.id))
    for i in range(3):
        db.session.add(
            SecurityEvent(
                organization_id=org.id,
                actor_id=admin.id,
                action=f"probe.event.{i}",
                resource_type="probe",
                resource_id=i,
                outcome="ok",
                correlation_id=uuid.uuid4().hex,
            )
        )
    db.session.commit()
    return {"org": org, "admin": admin}


class TestService:
    def test_slice_contains_expected_events(self, pg_app, seeded):
        from app.services import audit_chain_export

        signed = audit_chain_export.export_slice(
            organization_id=seeded["org"].id
        )
        events = signed.bundle["events"]
        probes = [e for e in events if e["action"].startswith("probe.event")]
        assert len(probes) == 3

    def test_anchor_prev_hash_present_when_rows(self, pg_app, seeded):
        from app.services import audit_chain_export

        signed = audit_chain_export.export_slice(
            organization_id=seeded["org"].id
        )
        # The first row's prev_event_hash is exposed as the anchor.
        first_event = signed.bundle["events"][0]
        assert signed.bundle["anchor_prev_hash"] == first_event["prev_event_hash"]

    def test_signature_round_trip(self, pg_app, seeded):
        from app.services import audit_chain_export

        priv, pub = _ed25519_pem_pair()
        pg_app.config["AUDIT_EXPORT_SIGNING_KEY"] = priv
        try:
            signed = audit_chain_export.export_slice(
                organization_id=seeded["org"].id
            )
            assert signed.signature_hex is not None
            assert audit_chain_export.verify_slice(
                signed.bundle, signed.signature_hex, public_key_pem=pub
            )
        finally:
            pg_app.config["AUDIT_EXPORT_SIGNING_KEY"] = None

    def test_tampered_bundle_fails_verification(self, pg_app, seeded):
        import json

        from app.services import audit_chain_export

        priv, pub = _ed25519_pem_pair()
        pg_app.config["AUDIT_EXPORT_SIGNING_KEY"] = priv
        try:
            signed = audit_chain_export.export_slice(
                organization_id=seeded["org"].id
            )
            tampered = json.loads(
                json.dumps(signed.bundle, default=str)
            )
            tampered["events"][0]["action"] = "forged"
            assert not audit_chain_export.verify_slice(
                tampered, signed.signature_hex, public_key_pem=pub
            )
        finally:
            pg_app.config["AUDIT_EXPORT_SIGNING_KEY"] = None

    def test_max_rows_cap(self, pg_app, seeded):
        import uuid

        from app.extensions import db
        from app.models.event_delivery import SecurityEvent
        from app.services import audit_chain_export

        for i in range(20):
            db.session.add(
                SecurityEvent(
                    organization_id=seeded["org"].id,
                    actor_id=seeded["admin"].id,
                    action="bulk.probe",
                    resource_type="probe",
                    resource_id=i,
                    outcome="ok",
                    correlation_id=uuid.uuid4().hex,
                )
            )
        db.session.commit()
        signed = audit_chain_export.export_slice(
            organization_id=seeded["org"].id, max_rows=5
        )
        assert signed.bundle["row_count"] == 5
        assert signed.bundle["truncated"] is True


class TestApi:
    def test_admin_exports(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["admin"].id))
        r = client.get(
            "/api/_internal/audit/export",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        body = r.get_json()
        assert body["bundle"]["row_count"] >= 3

    def test_non_admin_forbidden(self, pg_app, seeded):
        from app.extensions import db
        from app.models.user import User

        regular = User(
            username="audit-regular",
            email="audit-regular@example.test",
            is_active=True,
            organization_id=seeded["org"].id,
        )
        regular.set_password("auditpassword12345")
        db.session.add(regular)
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(regular.id))
        r = client.get(
            "/api/_internal/audit/export",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403
