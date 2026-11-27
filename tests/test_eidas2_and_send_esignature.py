"""End-to-end tests for eIDAS 2.0 (SES / AES / QES, CSC API v2, EUDI Wallet,
ETSI EN 319 412-5 QCStatements, PAdES-B-LTA), SignNow-grade Send-for-eSignature
workflows, Bulk Invites, Shareable Links, Hash-Chained Certificate of Completion,
and removal of the deprecated Trust disclaimer.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app import create_app
from app.extensions import db
from app.models.eidas_signature import SignatureWorkflowPackage, ensure_eidas_tables
from app.models.organization import Organization
from app.models.user import User


@pytest.fixture()
def app_client(pg_app):
    pg_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    ensure_eidas_tables()
    org = Organization(name="eIDAS Test Org")
    db.session.add(org)
    db.session.flush()
    user = User(
        username="eidas_admin",
        email="eidas.admin@trustseal.local",
        first_name="eIDAS",
        last_name="Admin",
        organization_id=org.id,
        is_active=True,
    )
    user.set_password("trustseal-eidas-pass-2026")
    db.session.add(user)
    db.session.commit()

    client = pg_app.test_client()
    login = client.post(
        "/api/auth/login",
        json={"identifier": user.email, "password": "trustseal-eidas-pass-2026"},
    )
    assert login.status_code == 200, login.get_json()
    token = login.get_json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Requested-With": "fetch"}
    yield pg_app, client, headers


def test_trust_page_removes_old_disclaimer_and_documents_eidas2(app_client):
    _app, client, _headers = app_client
    resp = client.get("/trust")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "What TRUSTSEAL does" not in body
    assert "does not represent the current build" not in body
    assert "eIDAS 2.0" in body
    assert "Qualified Electronic Signature" in body
    assert "PAdES-B-LTA" in body
    assert "EUDI Wallet" in body


def test_eidas_standards_and_qtsp_and_certificate_inspection(app_client):
    _app, client, headers = app_client

    r = client.get("/api/eidas/standards", headers=headers)
    assert r.status_code == 200
    data = r.get_json()
    assert set(data["signature_levels"].keys()) == {"SES", "AES", "QES"}
    assert set(data["pades_profiles"].keys()) == {"PAdES-B-B", "PAdES-B-T", "PAdES-B-LT", "PAdES-B-LTA"}
    assert len(data["qtsp_providers"]) >= 1

    # Generate a synthetic X.509 certificate with ETSI EN 319 412-5 QCStatements
    # (QcCompliance 0.4.0.1862.1.1 + QcSSCD 0.4.0.1862.1.4 + QcType esign 0.4.0.1862.1.6.1)
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "QES Test Signer"), x509.NameAttribute(NameOID.COUNTRY_NAME, "NL")])
    qc_payload = b"\x30\x24\x30\x08\x06\x06\x04\x00\x8e\x46\x01\x01\x30\x08\x06\x06\x04\x00\x8e\x46\x01\x04\x30\x0e\x06\x06\x04\x00\x8e\x46\x01\x06\x30\x04\x06\x07\x04\x00\x8e\x46\x01\x06\x01"
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(dt.datetime.utcnow() - dt.timedelta(days=1))
        .not_valid_after(dt.datetime.utcnow() + dt.timedelta(days=365))
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=True, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.UnrecognizedExtension(x509.ObjectIdentifier("1.3.6.1.5.5.7.1.3"), qc_payload),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    pem = cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    insp = client.post("/api/eidas/certificates/inspect", json={"certificate_pem": pem})
    assert insp.status_code == 200
    info = insp.get_json()["inspection"]
    assert info["qc_compliance"] is True
    assert info["qc_sscd_qscd"] is True
    assert info["qc_type"] == "esign"
    assert info["eidas_classification"] == "QES"


def test_csc_v2_and_eudi_wallet_and_sequential_qes_completion(app_client):
    _app, client, headers = app_client

    # 1. Dispatch a 2-step sequential package: Step 1 = AES (OTP), Step 2 = QES (EUDI Wallet)
    create = client.post(
        "/api/esignatures/send",
        headers=headers,
        json={
            "title": "EU Master Services Agreement — eIDAS 2.0 Test",
            "routing_mode": "sequential",
            "eidas_level": "QES",
            "pades_profile": "PAdES-B-LTA",
            "expires_in_days": 45,
            "reminder_every_days": 2,
            "recipients": [
                {"name": "Jane AES", "email": "jane.aes@example.eu", "role": "signer", "signing_order": 1, "eidas_level": "AES", "auth_method": "email_otp"},
                {"name": "Pieter QES", "email": "pieter.qes@example.nl", "role": "signer", "signing_order": 2, "eidas_level": "QES", "auth_method": "eudi_wallet_pid"},
            ],
        },
    )
    assert create.status_code == 201, create.get_json()
    pkg = create.get_json()["package"]
    pkg_id = pkg["id"]
    pkg_ref = pkg["package_ref"]
    rec1, rec2 = pkg["recipients"][0], pkg["recipients"][1]
    assert rec1["status"] == "sent"
    assert rec2["status"] == "pending"

    tok1 = rec1["sign_url"].split("/")[-1]
    tok2 = rec2["sign_url"].split("/")[-1]

    # Step 2 signer cannot jump ahead of sequential order
    early = client.post(f"/api/esignatures/sign/{tok2}/complete", json={"consent_accepted": True, "qscd_pin": "9988"})
    assert early.status_code == 409

    # Step 1 AES signer requests OTP & signs
    otp_resp = client.post(f"/api/esignatures/sign/{tok1}/otp")
    assert otp_resp.status_code == 200
    otp_code = otp_resp.get_json()["demo_otp"]
    sign1 = client.post(f"/api/esignatures/sign/{tok1}/complete", json={"consent_accepted": True, "otp_code": otp_code})
    assert sign1.status_code == 200, sign1.get_json()
    assert sign1.get_json()["package"]["status"] == "in_progress"
    assert sign1.get_json()["package"]["recipients"][1]["status"] == "sent"

    # Reminder works while in_progress
    rem = client.post(f"/api/esignatures/send/{pkg_id}/remind", headers=headers)
    assert rem.status_code == 200
    assert rem.get_json()["reminders_sent"] == 1

    # Step 2 QES signer completes via EUDI Wallet ARF OpenID4VP session
    eudi_start = client.post("/api/eidas/eudi-wallet/sessions", json={"invite_token": tok2, "purpose": "qes_signing"})
    assert eudi_start.status_code == 201
    sid = eudi_start.get_json()["session"]["session_id"]
    assert eudi_start.get_json()["session"]["openid4vp_uri"].startswith("openid4vp://authorize?")

    eudi_cb = client.post(
        f"/api/eidas/eudi-wallet/sessions/{sid}/callback",
        json={"given_name": "Pieter", "family_name": "van Dijk", "issuing_country": "NL", "loa_verified": "high"},
    )
    assert eudi_cb.status_code == 200
    assert eudi_cb.get_json()["session"]["status"] == "signed"

    sign2 = client.post(f"/api/esignatures/sign/{tok2}/complete", json={"consent_accepted": True, "eudi_session_id": sid})
    assert sign2.status_code == 200, sign2.get_json()
    done_pkg = sign2.get_json()["package"]
    assert done_pkg["status"] == "completed"
    assert done_pkg["sealed_pdf_sha256"]
    assert done_pkg["tsa_token_digest"]
    assert done_pkg["lta_archive_digest"]
    assert done_pkg["ocsp_status"] == "good"

    # Public verification & printable Certificate of Completion
    ver = client.get(f"/api/esignatures/verify/{pkg_ref}")
    assert ver.status_code == 200
    assert ver.get_json()["verified"] is True
    assert ver.get_json()["certificate"]["audit_chain"]["intact"] is True

    cert_html = client.get(f"/esignatures/certificate/{pkg_ref}")
    assert cert_html.status_code == 200

    # CSC API v2 standalone SCAL2 SAD + signHash verification
    creds = client.post("/api/eidas/csc/v2/credentials/list", json={"signer_email": "pieter.qes@example.nl"})
    assert creds.status_code == 200
    cred_id = creds.get_json()["credentialIDs"][0]
    h_b64 = base64.b64encode(hashlib.sha256(b"csc-v2-doc").digest()).decode("ascii")
    auth_r = client.post("/api/eidas/csc/v2/credentials/authorize", json={"credentialID": cred_id, "hash": [h_b64], "PIN": "4321", "signer_email": "pieter.qes@example.nl"})
    assert auth_r.status_code == 200
    sad = auth_r.get_json()["SAD"]
    sig_r = client.post("/api/eidas/csc/v2/signatures/signHash", json={"credentialID": cred_id, "SAD": sad, "hash": [h_b64]})
    assert sig_r.status_code == 200
    assert len(sig_r.get_json()["signatures"]) == 1

    # Cleanup test record
    with _app.app_context():
        p = db.session.get(SignatureWorkflowPackage, pkg_id)
        if p:
            db.session.delete(p)
            db.session.commit()


def test_bulk_invite_csv_dispatch(app_client):
    app, client, headers = app_client
    csv_body = "name,email,role,eidas_level\nAlice One,alice1@example.eu,signer,QES\nBob Two,bob2@example.eu,signer,AES\n"
    res = client.post(
        "/api/esignatures/send/bulk",
        headers=headers,
        json={"title": "2026 Annual NDA Policy", "eidas_level": "AES", "csv_text": csv_body},
    )
    assert res.status_code == 201, res.get_json()
    data = res.get_json()
    assert data["dispatched_count"] == 2
    assert data["bulk_batch_id"].startswith("BULK-")
    ids = [p["id"] for p in data["packages"]]

    with app.app_context():
        for pid in ids:
            p = db.session.get(SignatureWorkflowPackage, pid)
            if p:
                db.session.delete(p)
        db.session.commit()
