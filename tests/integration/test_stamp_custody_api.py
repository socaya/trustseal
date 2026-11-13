"""PostgreSQL-backed governed stamp authority and approval integration tests.

Runs in CI on disposable PostgreSQL initialized from its guarded baseline.
PDF cryptography is mocked only for these authorization flows; the signing
integration suite validates real pyHanko artifacts independently.
"""
import uuid
from datetime import datetime

from flask_jwt_extended import create_access_token
from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.organization import Organization
from app.models.system import Role, UserRole
from app.models.stamp_custody import ManagedStamp
from app.models.documents.document import Document
from app.models.documents.document_blob import DocumentBlob
from app.models.signing_envelope import SigningEnvelope
from app.models.pdf_finalization import FinalizedPdf


def test_governed_stamp_approval_and_cross_tenant_guards(monkeypatch):
    app = create_app()
    with app.app_context():
        suffix = uuid.uuid4().hex[:10]
        org = Organization(name="Stamp Test " + suffix, type="company")
        other = Organization(name="Other Stamp Test " + suffix, type="company")
        db.session.add_all([org, other])
        db.session.flush()

        def user(label, organization):
            account = User(
                username=label + suffix,
                email=label + suffix + "@example.invalid",
                organization_id=organization.id, is_active=True,
            )
            account.set_password("test-only-strong-password")
            db.session.add(account)
            db.session.flush()
            return account

        requester = user("stampreq", org)
        custodian = user("stampcust", org)
        reviewer = user("stampreview", org)
        foreign = user("stampforeign", other)
        role = Role.query.filter_by(name="admin").first()
        if role is None:
            role = Role(name="admin", description="Test administrator")
            db.session.add(role)
            db.session.flush()
        db.session.add(UserRole(user_id=reviewer.id, role_id=role.id))
        db.session.commit()
        tokens = {
            label: {"Authorization": "Bearer " + create_access_token(identity=str(account.id))}
            for label, account in (
                ("requester", requester),
                ("custodian", custodian),
                ("reviewer", reviewer),
                ("foreign", foreign),
            )
        }
        client = app.test_client()

        response = client.post(
            "/api/stamp-custody",
            json={"code": "OFFICIAL-001", "name": "Office Verification", "custodian_id": custodian.id},
            headers=tokens["requester"],
        )
        assert response.status_code == 201, response.get_data(as_text=True)
        stamp_id = response.get_json()["id"]
        assert response.get_json()["status"] == "pending"
        assert client.post(
            "/api/stamp-custody/%s/approve" % stamp_id,
            headers=tokens["requester"],
        ).status_code == 403
        assert client.post(
            "/api/stamp-custody/%s/approve" % stamp_id,
            headers=tokens["foreign"],
        ).status_code in (403, 404)
        assert client.post(
            "/api/stamp-custody/%s/approve" % stamp_id,
            headers=tokens["reviewer"],
        ).status_code == 200
        assert client.post(
            "/api/stamp-custody/%s/approve" % stamp_id,
            headers=tokens["reviewer"],
        ).status_code == 409
        assert client.get(
            "/api/stamp-custody", headers=tokens["foreign"]
        ).get_json() == []
        assert client.get(
            "/api/stamp-custody", headers=tokens["custodian"]
        ).get_json()[0]["id"] == stamp_id

        doc = Document(
            title="Stamp issue document", created_by=custodian.id,
            organization_id=org.id, status="draft", version=1,
        )
        db.session.add(doc)
        db.session.flush()
        blob = DocumentBlob(
            document_id=doc.id, revision=1,
            object_key=uuid.uuid4().hex * 2 + ".pdf",
            file_name="stamp.pdf", mime_type="application/pdf", file_size=100,
            sha256="a" * 64, scanner="unit-test", created_by_id=custodian.id,
        )
        db.session.add(blob)
        db.session.flush()
        envelope = SigningEnvelope(
            organization_id=org.id, document_id=doc.id,
            document_blob_id=blob.id, document_sha256=blob.sha256,
            created_by_id=custodian.id, state="draft",
        )
        db.session.add(envelope)
        db.session.flush()
        envelope.state = "prepared"
        envelope.prepared_at = datetime.utcnow()
        db.session.flush()
        pdf = FinalizedPdf(
            envelope_id=envelope.id, organization_id=org.id,
            issued_by_id=reviewer.id, source_blob_id=blob.id,
            source_sha256=blob.sha256, evidence_sha256="b" * 64,
            object_key=uuid.uuid4().hex * 2 + ".pdf",
            output_sha256="c" * 64, output_size=1024,
            certificate_sha256="d" * 64, signature_field="TrustSealPlatformSeal",
            profile="platform_pades_b_b",
        )
        db.session.add(pdf)
        db.session.commit()

        from app.blueprints.estamp import stamp_custody_api
        monkeypatch.setattr(stamp_custody_api, "_verify_finalized_artifact", lambda _: None)
        response = client.post(
            "/api/stamp-custody/%s/applications" % stamp_id,
            json={"finalized_pdf_id": pdf.id, "reason": "Authorized document verification"},
            headers=tokens["custodian"],
        )
        assert response.status_code == 201, response.get_data(as_text=True)
        application_id = response.get_json()["id"]
        assert client.post(
            "/api/stamp-custody/applications/%s/decision" % application_id,
            json={"decision": "approved"}, headers=tokens["custodian"],
        ).status_code == 403
        response = client.post(
            "/api/stamp-custody/applications/%s/decision" % application_id,
            json={"decision": "approved"}, headers=tokens["reviewer"],
        )
        assert response.status_code == 200, response.get_data(as_text=True)
        assert response.get_json()["status"] == "approved"
        assert client.post(
            "/api/stamp-custody/applications/%s/decision" % application_id,
            json={"decision": "rejected"}, headers=tokens["reviewer"],
        ).status_code == 409
        assert client.post(
            "/api/stamp-custody/%s/revoke" % stamp_id,
            headers=tokens["reviewer"],
        ).status_code == 200
        assert ManagedStamp.query.get(stamp_id).status == "revoked"
        assert client.post(
            "/api/stamp-custody/%s/applications" % stamp_id,
            json={"finalized_pdf_id": pdf.id, "reason": "Cannot reuse after revocation"},
            headers=tokens["custodian"],
        ).status_code == 403
