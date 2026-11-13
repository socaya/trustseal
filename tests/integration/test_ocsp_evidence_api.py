"""PostgreSQL authorization and fail-closed OCSP evidence export tests."""
import base64
import uuid
from datetime import datetime, timedelta

from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db
from app.models.organization import Organization
from app.models.user import User
from app.models.system import Role, UserRole
from app.models.evidence_preservation import EvidenceRetention
from app.models.evidence_timestamp import EvidenceTimestamp
from app.models.ocsp_evidence import OcspEvidence


def test_ocsp_routes_isolate_tenants_and_reject_unverified_export():
    app = create_app()
    with app.app_context():
        suffix = uuid.uuid4().hex[:10]
        own = Organization(name="OCSP operator " + suffix, type="company")
        foreign = Organization(name="OCSP foreign " + suffix, type="company")
        db.session.add_all([own, foreign])
        db.session.flush()

        def account(label, tenant):
            user = User(
                username=label + suffix,
                email=label + suffix + "@example.invalid",
                organization_id=tenant.id, is_active=True,
            )
            user.set_password("disposable-ocsp-test-secret")
            db.session.add(user)
            db.session.flush()
            return user

        admin = account("ocspadmin", own)
        outsider = account("ocspoutside", foreign)
        role = Role.query.filter_by(name="admin").first()
        if role is None:
            role = Role(name="admin", description="isolated CI administrator")
            db.session.add(role)
            db.session.flush()
        db.session.add_all([
            UserRole(user_id=admin.id, role_id=role.id),
            UserRole(user_id=outsider.id, role_id=role.id),
        ])
        retention = EvidenceRetention(
            organization_id=own.id, artifact_type="finalized_pdf",
            artifact_id=1000000000 + int(suffix[:6], 16),
            artifact_sha256="a" * 64,
            retain_until=datetime.utcnow() + timedelta(days=3650),
            created_by_id=admin.id,
        )
        db.session.add(retention)
        db.session.flush()
        timestamp = EvidenceTimestamp(
            retention_id=retention.id, organization_id=own.id,
            operator_id=admin.id,
            artifact_sha256="a" * 64,
            tsa_certificate_sha256="b" * 64,
            token_sha256="c" * 64,
            token_der_b64=base64.b64encode(b"not-a-real-tsr").decode(),
            gen_time=datetime.utcnow(),
        )
        db.session.add(timestamp)
        db.session.flush()
        record = OcspEvidence(
            organization_id=own.id, timestamp_id=timestamp.id,
            operator_id=admin.id,
            subject_certificate_sha256="b" * 64,
            issuer_certificate_sha256="d" * 64,
            response_sha256="e" * 64,
            response_der_b64=base64.b64encode(b"not-a-real-ocsp").decode(),
            subject_der_b64=base64.b64encode(b"subject").decode(),
            issuer_der_b64=base64.b64encode(b"issuer").decode(),
            produced_at=datetime.utcnow() - timedelta(hours=1),
            this_update=datetime.utcnow() - timedelta(days=1),
            next_update=datetime.utcnow() + timedelta(days=1),
            checked_at=datetime.utcnow(), status="good",
        )
        db.session.add(record)
        db.session.commit()
        client = app.test_client()

        def header(user):
            return {"Authorization": "Bearer " + create_access_token(identity=str(user.id))}

        listing = "/api/evidence-preservation/timestamps/%s/ocsp" % timestamp.id
        export = "/api/evidence-preservation/ocsp/%s/export" % record.id
        response = client.get(listing, headers=header(admin))
        assert response.status_code == 200
        assert response.get_json()[0]["id"] == record.id
        assert "response_der_b64" not in response.get_json()[0]
        assert client.get(listing, headers=header(outsider)).status_code == 404
        assert client.get(export, headers=header(outsider)).status_code == 404
        # The token and response are deliberately fabricated. A real tenant
        # administrator must not obtain an unverified evidence export.
        assert client.get(export, headers=header(admin)).status_code == 409
