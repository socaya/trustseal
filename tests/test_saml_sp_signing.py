"""SP-signed SAML AuthnRequests (H3).

Covers:

* When ``sp_signing_private_key_pem`` + ``sp_signing_cert_pem`` are
  set on the provider, ``build_authn_request`` returns a URL whose
  ``Signature`` parameter is a valid RSA-SHA256 signature over the
  canonical query string (``SAMLRequest`` + ``RelayState`` +
  ``SigAlg``, in that order).
* Without signing credentials the behavior is unchanged (no
  ``SigAlg``/``Signature`` present).
* Metadata reflects ``AuthnRequestsSigned='true'`` and embeds the
  base64 certificate when signing is enabled; ``false`` otherwise.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID


def _generate_sp_credential():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "Disposable SP Signing")]
    )
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        )
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    return key_pem.decode("ascii"), cert_pem.decode("ascii"), key, cert


@pytest.fixture
def provider_with_signing(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.saml_provider import SamlProvider
    from app.models.user import User

    key_pem, cert_pem, key, cert = _generate_sp_credential()
    org = Organization(name="SAML Signing Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    admin = User(
        username="saml-sign-admin",
        email="saml-sign-admin@example.test",
        is_active=True,
        organization_id=org.id,
    )
    admin.set_password("samlsignpassword12345")
    db.session.add(admin)
    db.session.flush()
    provider = SamlProvider(
        organization_id=org.id,
        display_name="Signed IdP",
        entity_id="https://idp.example.test/signed",
        sso_url="https://idp.example.test/sso",
        x509_cert_pem=cert_pem,  # unused for Response path in this test
        audience="trustseal-sp-signed",
        attribute_mapping={"email": "email"},
        is_active=True,
        sp_signing_private_key_pem=key_pem,
        sp_signing_cert_pem=cert_pem,
        created_by_id=admin.id,
    )
    db.session.add(provider)
    db.session.commit()
    pg_app.config["PUBLIC_BASE_URL"] = "http://localhost.test"
    return {
        "provider": provider,
        "public_key": cert.public_key(),
    }


@pytest.fixture
def provider_without_signing(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.saml_provider import SamlProvider
    from app.models.user import User

    _, cert_pem, _, _ = _generate_sp_credential()
    org = Organization(name="SAML No-Sign Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    admin = User(
        username="saml-nosign-admin",
        email="saml-nosign-admin@example.test",
        is_active=True,
        organization_id=org.id,
    )
    admin.set_password("samlnopassword12345")
    db.session.add(admin)
    db.session.flush()
    provider = SamlProvider(
        organization_id=org.id,
        display_name="Unsigned IdP",
        entity_id="https://idp.example.test/plain",
        sso_url="https://idp.example.test/sso",
        x509_cert_pem=cert_pem,
        audience="trustseal-sp-plain",
        attribute_mapping={"email": "email"},
        is_active=True,
        created_by_id=admin.id,
    )
    db.session.add(provider)
    db.session.commit()
    pg_app.config["PUBLIC_BASE_URL"] = "http://localhost.test"
    return provider


class TestSignedAuthnRequest:
    def test_signature_present_and_valid(self, pg_app, provider_with_signing):
        from app.services.saml import SIG_ALG_RSA_SHA256, build_authn_request
        from urllib.parse import urlencode

        provider = provider_with_signing["provider"]
        url, _ = build_authn_request(
            provider,
            acs_url=f"http://localhost.test/saml/{provider.id}/acs",
            relay_state="/dashboard",
        )
        parts = urlparse(url)
        q = parse_qs(parts.query)
        assert "SAMLRequest" in q
        assert q["SigAlg"][0] == SIG_ALG_RSA_SHA256
        assert "Signature" in q
        # Rebuild the canonical signable string the same way the
        # service did and verify the signature.
        canonical = urlencode(
            [
                ("SAMLRequest", q["SAMLRequest"][0]),
                ("RelayState", q["RelayState"][0]),
                ("SigAlg", q["SigAlg"][0]),
            ]
        )
        provider_with_signing["public_key"].verify(
            base64.b64decode(q["Signature"][0]),
            canonical.encode("ascii"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )

    def test_unsigned_provider_has_no_signature(
        self, pg_app, provider_without_signing
    ):
        from app.services.saml import build_authn_request

        url, _ = build_authn_request(
            provider_without_signing,
            acs_url=f"http://localhost.test/saml/{provider_without_signing.id}/acs",
            relay_state="/here",
        )
        parts = urlparse(url)
        q = parse_qs(parts.query)
        assert "SAMLRequest" in q
        assert "Signature" not in q
        assert "SigAlg" not in q


class TestMetadata:
    def test_metadata_marks_signed_when_sp_cert_present(
        self, pg_app, provider_with_signing
    ):
        provider = provider_with_signing["provider"]
        client = pg_app.test_client()
        r = client.get(f"/saml/{provider.id}/metadata")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert 'AuthnRequestsSigned="true"' in body
        assert "<ds:X509Certificate" in body

    def test_metadata_marks_unsigned_when_no_sp_cert(
        self, pg_app, provider_without_signing
    ):
        client = pg_app.test_client()
        r = client.get(f"/saml/{provider_without_signing.id}/metadata")
        body = r.get_data(as_text=True)
        assert 'AuthnRequestsSigned="false"' in body
        assert "<ds:X509Certificate" not in body
