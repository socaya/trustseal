"""PostgreSQL-scoped CRL evidence export without tenant leakage.

Cryptographic chain validation is covered with real generated certificates
in tests/test_certificate_revocation.py; these tests isolate route policy.
"""
import base64
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.organization import Organization
from app.models.system import Role, UserRole
from app.models.evidence_preservation import EvidenceRetention
from app.models.evidence_timestamp import EvidenceTimestamp
from app.models.certificate_revocation import CertificateRevocationEvidence


def test_crl_evidence_listing_and_export_reject_foreign_admin(tmp_path):
    app = create_app()
    with app.app_context():
        postfix = uuid.uuid4().hex[:10]
        org = Organization(name="CRL tenant " + postfix, type="company")
        other = Organization(name="CRL foreign " + postfix, type="company")
        db.session.add_all([org, other])
        db.session.flush()

        def person(name, organization):
            user = User(
                username=name + postfix,
                email=name + postfix + "@example.invalid",
                organization_id=organization.id, is_active=True,
            )
            user.set_password("separate-test-password")
            db.session.add(user)
            db.session.flush()
            return user

        admin = person("crladmin", org)
        foreign = person("crlforeign", other)
        role = Role.query.filter_by(name="admin").first()
        if role is None:
            role = Role(name="admin", description="test administrator")
            db.session.add(role)
            db.session.flush()
        db.session.add_all([
            UserRole(user_id=admin.id, role_id=role.id),
            UserRole(user_id=foreign.id, role_id=role.id),
        ])
        retention = EvidenceRetention(
            organization_id=org.id, artifact_type="finalized_pdf",
            artifact_id=987654321, artifact_sha256="a" * 64,
            retain_until=datetime.utcnow() + timedelta(days=3650),
            created_by_id=admin.id,
        )
        db.session.add(retention)
        db.session.flush()
        timestamp = EvidenceTimestamp(
            retention_id=retention.id, organization_id=org.id,
            operator_id=admin.id, artifact_sha256="a" * 64,
            tsa_certificate_sha256="b" * 64,
            token_sha256="c" * 64,
            token_der_b64=base64.b64encode(b"test-tsa-response").decode(),
            gen_time=datetime.utcnow(),
        )
        db.session.add(timestamp)
        db.session.flush()
        evidence = CertificateRevocationEvidence(
            organization_id=org.id, timestamp_id=timestamp.id,
            operator_id=admin.id,
            subject_certificate_sha256="b" * 64,
            issuer_certificate_sha256="d" * 64,
            crl_sha256="e" * 64,
            crl_der_b64=base64.b64encode(b"test-crl").decode(),
            subject_der_b64=base64.b64encode(b"test-subject").decode(),
            issuer_der_b64=base64.b64encode(b"test-issuer").decode(),
            this_update=datetime.utcnow() - timedelta(days=1),
            next_update=datetime.utcnow() + timedelta(days=1),
            checked_at=datetime.utcnow(), status="good",
        )
        db.session.add(evidence)
        db.session.commit()
        client = app.test_client()

        def headers(who):
            return {"Authorization": "Bearer " + create_access_token(identity=str(who.id))}

        url = "/api/evidence-preservation/timestamps/%s/revocations" % timestamp.id
        response = client.get(url, headers=headers(admin))
        assert response.status_code == 200, response.get_data(as_text=True)
        assert response.get_json()[0]["crl_sha256"] == "e" * 64
        assert "crl_der_b64" not in response.get_json()[0]
        assert client.get(url, headers=headers(foreign)).status_code == 404
        exported_url = "/api/evidence-preservation/revocations/%s/export" % evidence.id
        assert client.get(exported_url, headers=headers(foreign)).status_code == 404
        with patch(
            "app.services.certificate_revocation.verify_snapshot",
            return_value={"subject_certificate_sha256": "b" * 64},
        ):
            # The API imports the service internally: even a valid admin must
            # have an approved root and verified signed CRL before export.
            assert client.get(exported_url, headers=headers(admin)).status_code == 409
