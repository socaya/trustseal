"""Tenant data export (K1)."""
from __future__ import annotations

import json

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
    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.organization import Organization
    from app.models.system import Role, UserRole
    from app.models.user import User

    org_a = Organization(name="Export A", type="company")
    org_b = Organization(name="Export B", type="company")
    db.session.add_all([org_a, org_b])
    db.session.flush()
    role = Role.query.filter_by(name="admin").one_or_none() or Role(
        name="admin", description="test"
    )
    db.session.add(role)
    db.session.flush()

    def mk_user(name, email, org, admin=False):
        u = User(
            username=name,
            email=email,
            is_active=True,
            organization_id=org.id,
        )
        u.set_password("exportpassword12345")
        db.session.add(u)
        db.session.flush()
        if admin:
            db.session.add(UserRole(user_id=u.id, role_id=role.id))
        return u

    admin_a = mk_user("export-admin", "export-admin@example.test", org_a, admin=True)
    foreign = mk_user("export-foreign", "export-foreign@example.test", org_b, admin=True)
    doc = Document(
        title="A doc",
        status="draft",
        created_by=admin_a.id,
        organization_id=org_a.id,
    )
    db.session.add(doc)
    db.session.commit()
    return {
        "org_a": org_a,
        "org_b": org_b,
        "admin": admin_a,
        "foreign": foreign,
        "doc": doc,
    }


class TestService:
    def test_bundle_contains_org_rows(self, pg_app, seeded):
        from app.services import tenant_export

        signed = tenant_export.export_tenant(seeded["org_a"].id)
        tables = signed.bundle["tables"]
        org_ids = {row["id"] for row in tables["organizations"]}
        assert org_ids == {seeded["org_a"].id}
        user_ids = {row["id"] for row in tables["users"]}
        assert seeded["admin"].id in user_ids
        assert seeded["foreign"].id not in user_ids
        doc_titles = {row["title"] for row in tables["documents"]}
        assert "A doc" in doc_titles

    def test_signature_verifies(self, pg_app, seeded):
        from app.services import tenant_export

        priv, pub = _ed25519_pem_pair()
        pg_app.config["TENANT_EXPORT_SIGNING_KEY"] = priv
        try:
            signed = tenant_export.export_tenant(seeded["org_a"].id)
            assert signed.signature_hex is not None
            assert tenant_export.verify_export(
                signed.bundle, signed.signature_hex, public_key_pem=pub
            )
        finally:
            pg_app.config["TENANT_EXPORT_SIGNING_KEY"] = None

    def test_verify_rejects_tampered(self, pg_app, seeded):
        from app.services import tenant_export

        priv, pub = _ed25519_pem_pair()
        pg_app.config["TENANT_EXPORT_SIGNING_KEY"] = priv
        try:
            signed = tenant_export.export_tenant(seeded["org_a"].id)
            tampered = json.loads(
                json.dumps(signed.bundle, default=str)
            )
            tampered["tables"]["organizations"][0]["name"] = "attacker"
            assert not tenant_export.verify_export(
                tampered, signed.signature_hex, public_key_pem=pub
            )
        finally:
            pg_app.config["TENANT_EXPORT_SIGNING_KEY"] = None

    def test_unsigned_when_no_key_configured(self, pg_app, seeded):
        from app.services import tenant_export

        pg_app.config["TENANT_EXPORT_SIGNING_KEY"] = None
        signed = tenant_export.export_tenant(seeded["org_a"].id)
        assert signed.signature_hex is None
        assert signed.signing_key_fingerprint is None
        assert signed.bundle_sha256


class TestApi:
    def test_admin_can_export_own_tenant(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["admin"].id))
        r = client.post(
            f"/api/organizations/{seeded['org_a'].id}/export",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        body = r.get_json()
        assert body["bundle_sha256"]
        assert body["bundle"]["organization_id"] == seeded["org_a"].id

    def test_cannot_export_foreign_tenant(self, pg_app, seeded):
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["admin"].id))
        r = client.post(
            f"/api/organizations/{seeded['org_b'].id}/export",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404
