"""Actual stamped PDF issuance integration: PostgreSQL, private storage and CMS.

Uses disposable test CA/Ed25519 keys and an isolated scanner fixture.
This is not production malware-scan, HSM or PKI validation.
"""
from datetime import datetime
from io import BytesIO
from pathlib import Path
import os
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from flask_jwt_extended import create_access_token
from pypdf import PdfReader

from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.organization import Organization
from app.models.system import Role, UserRole
from app.models.documents.document import Document
from app.models.documents.document_blob import DocumentBlob
from app.models.signing_envelope import SigningEnvelope
from app.models.pdf_finalization import FinalizedPdf
from app.models.stamp_custody import ManagedStamp, StampApplication, StampAttestation
from app.models.stamped_pdf import StampedPdf
from app.services.documents.private_storage import store_scanned_pdf
from app.services.platform_pdf_seal import seal_pdf
from app.services.stamp_attestation import stamp_payload, issue_attestation


def test_issue_visible_stamped_pdf_with_real_cms_and_verified_download(
    tmp_path, signing_config
):
    from reportlab.pdfgen import canvas
    app = create_app()
    root = tmp_path / "objects"
    root.mkdir(mode=0o700)
    scanner = tmp_path / "scanner-test-only"
    scanner.write_text("#!/bin/sh\nexit 0\n")
    scanner.chmod(0o700)
    app.config.update(
        signing_config,
        PRIVATE_DOCUMENT_ROOT=str(root),
        DOCUMENT_CLAMSCAN_BINARY=str(scanner),
        STAMP_PDF_RENDER_ENABLED=True,
        PDF_FINALIZATION_ENABLED=True,
    )
    with app.app_context():
        suffix = uuid.uuid4().hex[:10]
        org = Organization(name="Visible Stamp " + suffix, type="company")
        foreign_org = Organization(name="Foreign Stamp " + suffix, type="company")
        db.session.add_all([org, foreign_org])
        db.session.flush()

        def add_user(label, organization):
            account = User(
                username=label + suffix, email=label + suffix + "@example.invalid",
                organization_id=organization.id, is_active=True,
            )
            account.set_password("isolated-test-password")
            db.session.add(account)
            db.session.flush()
            return account

        creator = add_user("stampCreator", org)
        custodian = add_user("stampCust", org)
        approver = add_user("stampApprover", org)
        receipt_issuer = add_user("receiptIssuer", org)
        output_issuer = add_user("outputIssuer", org)
        outsider = add_user("outside", foreign_org)
        role = Role.query.filter_by(name="admin").first()
        if role is None:
            role = Role(name="admin", description="Temporary CI admin")
            db.session.add(role)
            db.session.flush()
        db.session.add(UserRole(user_id=output_issuer.id, role_id=role.id))

        draft = Document(
            title="Frozen source for stamp", created_by=creator.id,
            organization_id=org.id, status="draft", version=1,
        )
        db.session.add(draft)
        db.session.flush()

        unsigned_io = BytesIO()
        c = canvas.Canvas(unsigned_io, pagesize=(612, 792))
        c.drawString(70, 700, "Original frozen source for TrustSeal")
        c.showPage()
        c.save()
        unsigned = unsigned_io.getvalue()
        key, _, size, source_hash, scanner_id = store_scanned_pdf(
            BytesIO(unsigned), "original.pdf", app.config
        )
        blob = DocumentBlob(
            document_id=draft.id, revision=1,
            object_key=key, file_name="original.pdf", mime_type="application/pdf",
            file_size=size, sha256=source_hash, scanner=scanner_id,
            created_by_id=creator.id,
        )
        db.session.add(blob)
        db.session.flush()
        envelope = SigningEnvelope(
            organization_id=org.id, document_id=draft.id,
            document_blob_id=blob.id, document_sha256=blob.sha256,
            created_by_id=creator.id, state="draft",
        )
        db.session.add(envelope)
        db.session.flush()
        envelope.state = "prepared"
        envelope.prepared_at = datetime.utcnow()
        db.session.flush()

        review_digest = "b" * 64
        platform_signed, fingerprint, _ = seal_pdf(
            unsigned, app.config, review_digest
        )
        key, _, size, signed_hash, _ = store_scanned_pdf(
            BytesIO(platform_signed), "platform.pdf", app.config
        )
        original_signed = FinalizedPdf(
            envelope_id=envelope.id, organization_id=org.id,
            issued_by_id=approver.id, source_blob_id=blob.id,
            source_sha256=source_hash, evidence_sha256=review_digest,
            object_key=key, output_sha256=signed_hash, output_size=size,
            certificate_sha256=fingerprint, signature_field="TrustSealPlatformSeal",
            profile="platform_pades_b_b",
        )
        db.session.add(original_signed)
        db.session.flush()

        stamp = ManagedStamp(
            organization_id=org.id, code="VW-001",
            name="Vitalworks Limited", custodian_id=custodian.id,
            created_by_id=creator.id, approved_by_id=approver.id,
            status="active", approved_at=datetime.utcnow(),
        )
        db.session.add(stamp)
        db.session.flush()
        application = StampApplication(
            stamp_id=stamp.id, organization_id=org.id,
            finalized_pdf_id=original_signed.id,
            source_sha256=original_signed.output_sha256,
            evidence_sha256=review_digest,
            requested_by_id=custodian.id,
            reason="Board-authorized document stamp",
            status="approved", decided_by_id=approver.id,
            decided_at=datetime.utcnow(),
        )
        db.session.add(application)
        db.session.flush()

        stamp_private = Ed25519PrivateKey.generate()
        public_file = tmp_path / "stamp-public.pem"
        public_file.write_bytes(stamp_private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        ))
        app.config["STAMP_ATTESTATION_PUBLIC_KEY"] = str(public_file)
        app.config["STAMP_ATTESTATION_OPERATOR_ID"] = str(output_issuer.id)
        now = datetime.utcnow()
        signed_receipt = issue_attestation(
            stamp_payload(stamp, application, original_signed, receipt_issuer.id, now),
            stamp_private,
        )
        stamp_receipt = StampAttestation(
            application_id=application.id,
            stamp_id=stamp.id, organization_id=org.id,
            operator_id=receipt_issuer.id,
            payload=signed_receipt["payload"],
            algorithm=signed_receipt["algorithm"],
            key_id=signed_receipt["key_id"],
            signature=signed_receipt["signature"],
            created_at=now,
        )
        db.session.add(stamp_receipt)
        db.session.commit()
        receipt_id = stamp_receipt.id
        original_digest = original_signed.output_sha256

        cli = app.test_cli_runner().invoke(
            args=["stamped-pdf", "issue", str(receipt_id),
                  "--page", "1", "--x", "350", "--y", "60"]
        )
        assert cli.exit_code == 0, cli.output
        artifact = StampedPdf.query.filter_by(
            stamp_attestation_id=receipt_id
        ).one()
        assert artifact.source_finalized_sha256 == original_digest
        assert artifact.output_sha256 != original_digest

        token = create_access_token(identity=str(custodian.id))
        response = app.test_client().get(
            "/api/stamped-pdfs/%s/verify" % artifact.id,
            headers={"Authorization": "Bearer " + token},
        )
        assert response.status_code == 200, response.get_data(as_text=True)
        assert response.get_json()["valid"] is True
        response = app.test_client().get(
            "/api/stamped-pdfs/%s/download" % artifact.id,
            headers={"Authorization": "Bearer " + token},
        )
        assert response.status_code == 200, response.get_data(as_text=True)
        assert "Vitalworks Limited" in PdfReader(BytesIO(response.data)).pages[0].extract_text()
        outsider_token = create_access_token(identity=str(outsider.id))
        assert app.test_client().get(
            "/api/stamped-pdfs/%s/download" % artifact.id,
            headers={"Authorization": "Bearer " + outsider_token},
        ).status_code == 404

        duplicate = app.test_cli_runner().invoke(
            args=["stamped-pdf", "issue", str(receipt_id),
                  "--page", "1", "--x", "350", "--y", "60"]
        )
        assert duplicate.exit_code == 0
        assert "already exists" in duplicate.output
        assert StampedPdf.query.filter_by(stamp_attestation_id=receipt_id).count() == 1
