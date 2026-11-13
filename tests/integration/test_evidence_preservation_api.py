"""PostgreSQL-backed preservation retention and legal hold API tests."""
import uuid
from datetime import datetime

from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db
from app.models.organization import Organization
from app.models.user import User
from app.models.system import Role, UserRole
from app.models.documents.document import Document
from app.models.documents.document_blob import DocumentBlob
from app.models.signing_envelope import SigningEnvelope
from app.models.pdf_finalization import FinalizedPdf
from app.models.evidence_preservation import (
    EvidenceRetention, EvidenceLegalHold,
)


def test_tenant_retention_and_independent_hold_release(monkeypatch, tmp_path):
    app = create_app()
    with app.app_context():
        suffix = uuid.uuid4().hex[:10]
        tenant = Organization(name="Preservation " + suffix, type="company")
        foreign = Organization(name="External " + suffix, type="company")
        db.session.add_all([tenant, foreign])
        db.session.flush()

        def user(name, org):
            person = User(
                username=name + suffix,
                email=name + suffix + "@example.invalid",
                organization_id=org.id, is_active=True,
            )
            person.set_password("unique-testing-password")
            db.session.add(person)
            db.session.flush()
            return person

        author = user("presauthor", tenant)
        administrator = user("presadmin", tenant)
        independent = user("presindependent", tenant)
        outsider = user("presoutside", foreign)
        role = Role.query.filter_by(name="admin").first()
        if role is None:
            role = Role(name="admin", description="CI administrator")
            db.session.add(role)
            db.session.flush()
        db.session.add_all([
            UserRole(user_id=administrator.id, role_id=role.id),
            UserRole(user_id=independent.id, role_id=role.id),
            UserRole(user_id=outsider.id, role_id=role.id),
        ])
        draft = Document(
            title="Preservation source", created_by=author.id,
            organization_id=tenant.id, status="draft", version=1,
        )
        db.session.add(draft)
        db.session.flush()
        blob = DocumentBlob(
            document_id=draft.id, revision=1,
            object_key=uuid.uuid4().hex * 2 + ".pdf",
            file_name="stored.pdf", mime_type="application/pdf",
            file_size=128, sha256="a" * 64,
            scanner="test-only", created_by_id=author.id,
        )
        db.session.add(blob)
        db.session.flush()
        envelope = SigningEnvelope(
            organization_id=tenant.id, document_id=draft.id,
            document_blob_id=blob.id, document_sha256=blob.sha256,
            created_by_id=author.id, state="draft",
        )
        db.session.add(envelope)
        db.session.flush()
        envelope.state = "prepared"
        envelope.prepared_at = datetime.utcnow()
        db.session.flush()
        pdf = FinalizedPdf(
            envelope_id=envelope.id, organization_id=tenant.id,
            issued_by_id=author.id, source_blob_id=blob.id,
            source_sha256=blob.sha256, evidence_sha256="b" * 64,
            object_key=uuid.uuid4().hex * 2 + ".pdf",
            output_sha256="c" * 64, output_size=512,
            certificate_sha256="d" * 64,
            signature_field="TrustSealPlatformSeal", profile="platform_pades_b_b",
        )
        db.session.add(pdf)
        db.session.commit()
        client = app.test_client()

        def auth(who):
            return {"Authorization": "Bearer " + create_access_token(identity=str(who.id))}

        path = "/api/evidence-preservation/retentions"
        request = {"artifact_type": "finalized_pdf", "artifact_id": pdf.id,
                   "retention_days": 3650}
        assert client.post(path, json=request, headers=auth(author)).status_code == 403
        assert client.post(path, json=request, headers=auth(outsider)).status_code == 404
        response = client.post(path, json=request, headers=auth(administrator))
        assert response.status_code == 201, response.get_data(as_text=True)
        retention_id = response.get_json()["id"]
        assert response.get_json()["deletion_permitted"] is False
        assert client.post(path, json=request, headers=auth(administrator)).status_code == 409

        hold_path = "/api/evidence-preservation/retentions/%s/holds" % retention_id
        held = client.post(
            hold_path, json={"reason": "Active litigation preservation order"},
            headers=auth(administrator),
        )
        assert held.status_code == 201, held.get_data(as_text=True)
        hold_id = held.get_json()["id"]
        report = client.get(
            "/api/evidence-preservation/retentions/%s" % retention_id,
            headers=auth(administrator),
        )
        assert report.get_json()["active_legal_holds"] == 1
        release_path = "/api/evidence-preservation/holds/%s/release" % hold_id
        release = {"reason": "Court matter resolved and counsel authorized release"}
        assert client.post(
            release_path, json=release, headers=auth(administrator)
        ).status_code == 403
        assert client.post(release_path, json=release, headers=auth(outsider)).status_code == 404
        response = client.post(
            release_path, json={}, headers=auth(independent)
        )
        assert response.status_code == 200, response.get_data(as_text=True)
        assert response.get_json()["active"] is False
        released_hold = db.session.get(EvidenceLegalHold, hold_id)
        assert released_hold.release_reason == release["reason"]
        assert client.post(release_path, json={}, headers=auth(independent)).status_code == 409
        record = db.session.get(EvidenceRetention, retention_id)
        assert record.retain_until.year >= 2036
        assert EvidenceLegalHold.query.filter_by(retention_id=retention_id).count() == 1

        # A signed integrity checkpoint needs a separate authorized operator,
        # and may only be issued after the source PDF integrity check succeeds.
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        private = Ed25519PrivateKey.generate()
        pem = tmp_path / "preservation-private.pem"
        pem.write_bytes(private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        pem.chmod(0o600)
        public = tmp_path / "preservation-public.pem"
        public.write_bytes(private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        app.config.update(
            EVIDENCE_CHECKPOINT_ENABLED=True,
            EVIDENCE_CHECKPOINT_PRIVATE_KEY=str(pem),
            EVIDENCE_CHECKPOINT_PUBLIC_KEY=str(public),
            EVIDENCE_CHECKPOINT_OPERATOR_ID=str(independent.id),
        )
        import app.cli.preservation as preservation
        monkeypatch.setattr(
            preservation, "verify_artifact",
            lambda artifact, kind, config: artifact.output_sha256,
        )
        response = app.test_cli_runner().invoke(
            args=["preservation", "checkpoint", str(retention_id)]
        )
        assert response.exit_code == 0, response.output
        from app.models.evidence_preservation import EvidenceCheckpoint
        checkpoint = EvidenceCheckpoint.query.filter_by(
            retention_id=retention_id
        ).one()
        from app.services.evidence_preservation import (
            trusted_checkpoint_key, verify_checkpoint,
        )
        assert verify_checkpoint(
            {
                "payload": checkpoint.payload,
                "algorithm": checkpoint.algorithm,
                "key_id": checkpoint.key_id,
                "signature": checkpoint.signature,
            },
            trusted_checkpoint_key(app.config, checkpoint.key_id),
        )
        verify_result = app.test_cli_runner().invoke(
            args=["preservation", "verify", str(checkpoint.id)]
        )
        assert verify_result.exit_code == 0, verify_result.output
        exported = client.get(
            "/api/evidence-preservation/retentions/%s/checkpoints" % retention_id,
            headers=auth(administrator),
        )
        assert exported.status_code == 200
        assert exported.get_json()[0]["id"] == checkpoint.id
        assert client.get(
            "/api/evidence-preservation/retentions/%s/checkpoints" % retention_id,
            headers=auth(outsider),
        ).status_code == 404

