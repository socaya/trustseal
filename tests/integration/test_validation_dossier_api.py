"""Real PostgreSQL dossier lifecycle, auth separation and tamper rejection."""
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
from app.models.validation_dossier import ValidationDossier


def test_immutable_partial_dossier_issue_verify_and_tenant_export(monkeypatch):
    app = create_app()
    with app.app_context():
        nonce = uuid.uuid4().hex[:10]
        local = Organization(name="Dossier local " + nonce, type="company")
        foreign = Organization(name="Dossier foreign " + nonce, type="company")
        db.session.add_all([local, foreign])
        db.session.flush()

        def account(prefix, tenant):
            user = User(
                username=prefix + nonce,
                email=prefix + nonce + "@example.invalid",
                organization_id=tenant.id, is_active=True,
            )
            user.set_password("isolated-dossier-password")
            db.session.add(user)
            db.session.flush()
            return user

        author = account("dossierauthor", local)
        operator = account("dossieroperator", local)
        outsider = account("dossierforeign", foreign)
        admin_role = Role.query.filter_by(name="admin").first()
        if admin_role is None:
            admin_role = Role(name="admin", description="Dossier CI role")
            db.session.add(admin_role)
            db.session.flush()
        db.session.add_all([
            UserRole(user_id=operator.id, role_id=admin_role.id),
            UserRole(user_id=outsider.id, role_id=admin_role.id),
        ])
        retention = EvidenceRetention(
            organization_id=local.id, artifact_type="finalized_pdf",
            artifact_id=900000000 + int(nonce[:6], 16),
            artifact_sha256="a" * 64,
            retain_until=datetime.utcnow() + timedelta(days=3650),
            created_by_id=author.id,
        )
        db.session.add(retention)
        db.session.flush()
        timestamp = EvidenceTimestamp(
            organization_id=local.id, retention_id=retention.id,
            operator_id=operator.id, artifact_sha256=retention.artifact_sha256,
            tsa_certificate_sha256="b" * 64, token_sha256="c" * 64,
            token_der_b64="ignored-with-cryptographic-fixture",
            gen_time=datetime(2026, 11, 13, 9, 0, 0),
        )
        db.session.add(timestamp)
        db.session.commit()
        from app.services import validation_dossier as service
        from types import SimpleNamespace
        monkeypatch.setattr(service, "artifact_for", lambda *args: SimpleNamespace(
            output_sha256="a" * 64,
        ))
        monkeypatch.setattr(service, "verify_artifact", lambda *args: "a" * 64)
        monkeypatch.setattr(service, "decode_token", lambda *args: b"test-tsa-token")
        monkeypatch.setattr(service, "verify_timestamp", lambda *args: {
            "token_sha256": "c" * 64,
            "tsa_certificate_sha256": "b" * 64,
            "gen_time": datetime(2026, 11, 13, 9, 0, 0),
        })
        monkeypatch.setattr(service, "_read_pem", lambda *args: b"trusted-test-root")
        app.config.update(
            VALIDATION_DOSSIER_ENABLED=True,
            EVIDENCE_CHECKPOINT_OPERATOR_ID=str(operator.id),
        )
        run = app.test_cli_runner().invoke(
            args=["validation-dossier", "issue", str(timestamp.id)]
        )
        assert run.exit_code == 0, run.output
        dossier = ValidationDossier.query.filter_by(
            timestamp_id=timestamp.id
        ).one()
        assert dossier.manifest["complete"] is False
        verify = app.test_cli_runner().invoke(
            args=["validation-dossier", "verify", str(dossier.id)]
        )
        assert verify.exit_code == 0, verify.output
        client = app.test_client()

        def headers(person):
            return {
                "Authorization": "Bearer " + create_access_token(
                    identity=str(person.id)
                )
            }

        listing = "/api/evidence-preservation/retentions/%s/dossiers" % retention.id
        export = "/api/evidence-preservation/dossiers/%s/export" % dossier.id
        own = client.get(listing, headers=headers(operator))
        assert own.status_code == 200
        assert own.get_json()[0]["complete"] is False
        assert client.get(listing, headers=headers(outsider)).status_code == 404
        assert client.get(export, headers=headers(outsider)).status_code == 404
        good = client.get(export, headers=headers(operator))
        assert good.status_code == 200, good.get_data(as_text=True)
        assert good.get_json()["manifest_sha256"] == dossier.manifest_sha256
        assert good.get_json()["manifest"]["complete"] is False
        # The database forbids ordinary mutation of a finalized dossier.
        from sqlalchemy import text
        from sqlalchemy.exc import DatabaseError
        with __import__("pytest").raises(DatabaseError):
            db.session.execute(
                text("UPDATE validation_dossiers SET manifest_sha256=:sha WHERE id=:id"),
                {"sha": "f" * 64, "id": dossier.id},
            )
            db.session.flush()
        db.session.rollback()
