"""PostgreSQL-backed end-to-end signer-held endorsement API test.

Requires the disposable CI PostgreSQL database to have completed migration.
This test stubs ONLY the private object integrity check, so it exercises real
JWT authorization, PostgreSQL transactions, challenge consumption and Ed25519
verification. Private object scanning has a separate integration test gate.
"""
import base64
import hashlib
import uuid
from datetime import datetime, timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from flask_jwt_extended import create_access_token

from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.organization import Organization
from app.models.documents.document import Document
from app.models.documents.document_blob import DocumentBlob
from app.models.signing_envelope import SigningEnvelope, EnvelopeParticipant
from app.models.signer_decision import SignerChallenge, SignerDecision
from app.blueprints.documents.api.signer_intent_api import _decision_digest
from app.services.signer_crypto import canonical_message


def _signature(private_key, message):
    return base64.b64encode(
        private_key.sign(canonical_message(message))
    ).decode("ascii")


def test_signer_key_registration_endorsement_replay_and_revocation(monkeypatch):
    app = create_app()
    with app.app_context():
        suffix = uuid.uuid4().hex[:12]
        org = Organization(name="Signer Integration " + suffix, type="company")
        db.session.add(org)
        db.session.flush()
        signer = User(
            username="signer_" + suffix, email="signer_" + suffix + "@example.invalid",
            organization_id=org.id, is_active=True,
        )
        signer.set_password("valid-test-password-123")
        db.session.add(signer)
        db.session.flush()
        doc = Document(
            title="Signer integration test", created_by=signer.id,
            organization_id=org.id, status="draft", version=1,
        )
        db.session.add(doc)
        db.session.flush()
        blob = DocumentBlob(
            document_id=doc.id, revision=1, object_key=uuid.uuid4().hex * 2 + ".pdf",
            file_name="integration.pdf", mime_type="application/pdf",
            file_size=20, sha256="a" * 64, scanner="test-only",
            created_by_id=signer.id,
        )
        db.session.add(blob)
        db.session.flush()
        envelope = SigningEnvelope(
            document_id=doc.id, document_blob_id=blob.id,
            document_sha256=blob.sha256,
            organization_id=org.id, created_by_id=signer.id,
            state="draft",
        )
        db.session.add(envelope)
        db.session.flush()
        participant = EnvelopeParticipant(
            envelope_id=envelope.id, user_id=signer.id,
            signing_order=1, role="signer",
        )
        db.session.add(participant)
        db.session.flush()
        envelope.state = "prepared"
        envelope.prepared_at = datetime.utcnow()
        db.session.flush()
        now = datetime.utcnow()
        challenge = SignerChallenge(
            envelope_id=envelope.id, participant_id=participant.id,
            user_id=signer.id, nonce_sha256=hashlib.sha256(b"prior-intent").hexdigest(),
            document_sha256=blob.sha256, issued_at=now,
            expires_at=now + timedelta(minutes=10), consumed_at=now,
        )
        db.session.add(challenge)
        db.session.flush()
        decision = SignerDecision(
            envelope_id=envelope.id, participant_id=participant.id,
            user_id=signer.id, challenge_id=challenge.id,
            decision="acknowledged", document_sha256=envelope.document_sha256,
            consent_version="review-intent-v1",
            consent_sha256=_decision_digest(envelope, participant, signer.id, "acknowledged"),
            recorded_at=now,
        )
        db.session.add(decision)
        db.session.commit()
        envelope_id = envelope.id
        token = create_access_token(identity=str(signer.id))

        import app.blueprints.documents.api.signer_crypto_api as crypto_api
        monkeypatch.setattr(crypto_api, "_document_file", lambda _: (None, None))
        private = Ed25519PrivateKey.generate()
        public_pem = private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")

        client = app.test_client()
        headers = {"Authorization": "Bearer " + token}
        response = client.post(
            "/api/signer-crypto/keys/challenge",
            json={"public_key_pem": public_pem}, headers=headers,
        )
        assert response.status_code == 201, response.get_data(as_text=True)
        registration = response.get_json()
        response = client.post(
            "/api/signer-crypto/keys/confirm",
            json={
                "challenge_id": registration["challenge_id"],
                "nonce": registration["sign_this"]["nonce"],
                "signature_b64": _signature(private, registration["sign_this"]),
            },
            headers=headers,
        )
        assert response.status_code == 201, response.get_data(as_text=True)
        key_id = response.get_json()["id"]

        response = client.post(
            "/api/signer-crypto/envelopes/%s/challenge" % envelope_id,
            json={"key_id": key_id}, headers=headers,
        )
        assert response.status_code == 201, response.get_data(as_text=True)
        proof_request = response.get_json()
        body = {
            "challenge_id": proof_request["challenge_id"],
            "signature_b64": _signature(private, proof_request["sign_this"]),
        }
        route = "/api/signer-crypto/envelopes/%s/endorse" % envelope_id
        response = client.post(route, json=body, headers=headers)
        assert response.status_code == 201, response.get_data(as_text=True)
        assert response.get_json()["assurance"].endswith("not_pades")
        assert client.post(route, json=body, headers=headers).status_code == 409

        response = client.get(
            "/api/signer-crypto/envelopes/%s/endorsement" % envelope_id,
            headers=headers,
        )
        assert response.status_code == 200
        assert response.get_json()[0]["signature_valid"] is True
        response = client.post(
            "/api/signer-crypto/keys/%s/revoke" % key_id, headers=headers,
        )
        assert response.status_code == 200
        response = client.get(
            "/api/signer-crypto/envelopes/%s/endorsement" % envelope_id,
            headers=headers,
        )
        assert response.get_json()[0]["key_revoked"] is True
