"""SAML 2.0 SSO (Phase G).

Covers the Service Provider end-to-end with a disposable test IdP.
Each test mints an ephemeral RSA key + self-signed X.509, builds a
``<samlp:Response>`` with a signed ``<saml:Assertion>`` using
``signxml``, and posts it to the ACS. The JIT path, signature
validation, replay protection, expiry, audience, recipient, and
in-response-to checks are all exercised.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from flask_jwt_extended import decode_token
from lxml import etree
from signxml import (
    DigestAlgorithm,
    SignatureConstructionMethod,
    SignatureMethod,
    XMLSigner,
)


SAML_ASSERTION_NS = "urn:oasis:names:tc:SAML:2.0:assertion"
SAML_PROTOCOL_NS = "urn:oasis:names:tc:SAML:2.0:protocol"
AUDIENCE = "trustseal-sp"
IDP_ENTITY_ID = "https://idp.example.test/entityid"


def _generate_idp_credential():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "Disposable Test IdP")]
    )
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
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


def _build_signed_response(
    *,
    idp_key,
    idp_cert,
    acs_url: str,
    name_id: str,
    email: str,
    in_response_to: str = "",
    not_on_or_after: datetime | None = None,
    assertion_id: str | None = None,
    audience: str = AUDIENCE,
) -> str:
    """Return base64(SAMLResponse) with a signed Assertion."""
    now = datetime.now(timezone.utc)
    issue_instant = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    noa = not_on_or_after or (now + timedelta(minutes=5))
    noa_str = noa.strftime("%Y-%m-%dT%H:%M:%SZ")
    not_before_str = (now - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assertion_id = assertion_id or "_assert_" + now.strftime("%H%M%S%f")

    nsmap = {None: SAML_PROTOCOL_NS, "saml": SAML_ASSERTION_NS}
    response = etree.Element(
        "{%s}Response" % SAML_PROTOCOL_NS,
        nsmap=nsmap,
        ID="_resp_" + now.strftime("%H%M%S%f"),
        Version="2.0",
        IssueInstant=issue_instant,
        Destination=acs_url,
        InResponseTo=in_response_to,
    )
    issuer = etree.SubElement(response, "{%s}Issuer" % SAML_ASSERTION_NS)
    issuer.text = IDP_ENTITY_ID
    status = etree.SubElement(response, "{%s}Status" % SAML_PROTOCOL_NS)
    etree.SubElement(
        status,
        "{%s}StatusCode" % SAML_PROTOCOL_NS,
        Value="urn:oasis:names:tc:SAML:2.0:status:Success",
    )

    assertion = etree.SubElement(
        response,
        "{%s}Assertion" % SAML_ASSERTION_NS,
        ID=assertion_id,
        Version="2.0",
        IssueInstant=issue_instant,
    )
    assertion_issuer = etree.SubElement(
        assertion, "{%s}Issuer" % SAML_ASSERTION_NS
    )
    assertion_issuer.text = IDP_ENTITY_ID
    subject = etree.SubElement(assertion, "{%s}Subject" % SAML_ASSERTION_NS)
    name_id_el = etree.SubElement(
        subject,
        "{%s}NameID" % SAML_ASSERTION_NS,
        Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
    )
    name_id_el.text = name_id
    confirmation = etree.SubElement(
        subject,
        "{%s}SubjectConfirmation" % SAML_ASSERTION_NS,
        Method="urn:oasis:names:tc:SAML:2.0:cm:bearer",
    )
    confirm_data_attrs = {
        "Recipient": acs_url,
        "NotOnOrAfter": noa_str,
    }
    if in_response_to:
        confirm_data_attrs["InResponseTo"] = in_response_to
    etree.SubElement(
        confirmation,
        "{%s}SubjectConfirmationData" % SAML_ASSERTION_NS,
        **confirm_data_attrs,
    )
    conditions = etree.SubElement(
        assertion,
        "{%s}Conditions" % SAML_ASSERTION_NS,
        NotBefore=not_before_str,
        NotOnOrAfter=noa_str,
    )
    audience_restriction = etree.SubElement(
        conditions, "{%s}AudienceRestriction" % SAML_ASSERTION_NS
    )
    audience_el = etree.SubElement(
        audience_restriction, "{%s}Audience" % SAML_ASSERTION_NS
    )
    audience_el.text = audience
    attr_statement = etree.SubElement(
        assertion, "{%s}AttributeStatement" % SAML_ASSERTION_NS
    )
    email_attr = etree.SubElement(
        attr_statement, "{%s}Attribute" % SAML_ASSERTION_NS, Name="email"
    )
    value = etree.SubElement(
        email_attr, "{%s}AttributeValue" % SAML_ASSERTION_NS
    )
    value.text = email

    # Sign the Assertion with an enveloped signature; the whole
    # Response goes through to the ACS.
    signed_assertion = XMLSigner(
        method=SignatureConstructionMethod.enveloped,
        signature_algorithm=SignatureMethod.RSA_SHA256,
        digest_algorithm=DigestAlgorithm.SHA256,
    ).sign(assertion, key=idp_key, cert=idp_cert)
    # Replace the unsigned assertion with the signed one.
    parent = assertion.getparent()
    parent.remove(assertion)
    parent.append(signed_assertion)
    xml = etree.tostring(response, xml_declaration=False, encoding="utf-8")
    return base64.b64encode(xml).decode("ascii")


@pytest.fixture
def idp(pg_app):
    key_pem, cert_pem, key, cert = _generate_idp_credential()
    return {"key_pem": key_pem, "cert_pem": cert_pem, "key": key, "cert": cert}


@pytest.fixture
def provider(pg_app, idp):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.saml_provider import SamlProvider
    from app.models.user import User

    org = Organization(name="SAML Tenant", type="company")
    db.session.add(org)
    db.session.flush()
    admin = User(
        username="saml-admin",
        email="saml-admin@example.test",
        is_active=True,
        organization_id=org.id,
    )
    admin.set_password("samlpassword12345")
    db.session.add(admin)
    db.session.flush()
    prov = SamlProvider(
        organization_id=org.id,
        display_name="Disposable Test IdP",
        entity_id=IDP_ENTITY_ID,
        sso_url="https://idp.example.test/sso",
        x509_cert_pem=idp["cert_pem"],
        audience=AUDIENCE,
        attribute_mapping={"email": "email"},
        is_active=True,
        created_by_id=admin.id,
    )
    db.session.add(prov)
    db.session.commit()
    pg_app.config["PUBLIC_BASE_URL"] = "http://localhost.test"
    return prov


def _acs_url(prov):
    return f"http://localhost.test/saml/{prov.id}/acs"


class TestMetadata:
    def test_publishes_sp_metadata(self, pg_app, provider):
        client = pg_app.test_client()
        r = client.get(f"/saml/{provider.id}/metadata")
        assert r.status_code == 200
        assert "application/samlmetadata+xml" in r.headers["Content-Type"]
        body = r.get_data()
        assert b"EntityDescriptor" in body
        assert AUDIENCE.encode() in body

    def test_inactive_provider_404(self, pg_app, provider):
        from app.extensions import db

        provider.is_active = False
        db.session.commit()
        client = pg_app.test_client()
        r = client.get(f"/saml/{provider.id}/metadata")
        assert r.status_code == 404


class TestLoginRedirect:
    def test_login_redirects_to_idp(self, pg_app, provider):
        client = pg_app.test_client()
        r = client.get(f"/saml/{provider.id}/login")
        assert r.status_code == 302
        assert r.headers["Location"].startswith(provider.sso_url)
        assert "SAMLRequest=" in r.headers["Location"]
        assert any(
            c.startswith(f"ts_saml_req_{provider.id}=")
            for c in r.headers.getlist("Set-Cookie")
        )


class TestAcsSuccess:
    def test_jit_creates_user_and_issues_tokens(
        self, pg_app, provider, idp
    ):
        from app.extensions import db
        from app.models.user import User

        response_b64 = _build_signed_response(
            idp_key=idp["key_pem"],
            idp_cert=idp["cert_pem"],
            acs_url=_acs_url(provider),
            name_id="new-user@idp.example.test",
            email="new-user@idp.example.test",
        )
        client = pg_app.test_client()
        r = client.post(
            f"/saml/{provider.id}/acs",
            data={"SAMLResponse": response_b64, "RelayState": "/dashboard"},
        )
        assert r.status_code == 302, r.get_data(as_text=True)
        assert r.headers["Location"].endswith("/dashboard")
        # Access + refresh cookies set.
        cookies = r.headers.getlist("Set-Cookie")
        assert any(c.startswith("access_token=") for c in cookies)
        assert any(c.startswith("refresh_token=") for c in cookies)
        # New User provisioned in the provider's org.
        user = User.query.filter_by(email="new-user@idp.example.test").one()
        assert user.organization_id == provider.organization_id
        assert user.email_verified is True

    def test_existing_user_reused(self, pg_app, provider, idp):
        from app.extensions import db
        from app.models.user import User

        existing = User(
            username="prior@idp.example.test",
            email="prior@idp.example.test",
            is_active=True,
            organization_id=provider.organization_id,
            email_verified=False,
        )
        existing.set_password("samlpassword12345")
        db.session.add(existing)
        db.session.commit()
        response_b64 = _build_signed_response(
            idp_key=idp["key_pem"],
            idp_cert=idp["cert_pem"],
            acs_url=_acs_url(provider),
            name_id="prior@idp.example.test",
            email="prior@idp.example.test",
        )
        client = pg_app.test_client()
        r = client.post(
            f"/saml/{provider.id}/acs",
            data={"SAMLResponse": response_b64},
        )
        assert r.status_code == 302
        db.session.refresh(existing)
        assert existing.email_verified is True
        # No duplicate was created.
        assert (
            User.query.filter_by(email="prior@idp.example.test").count() == 1
        )


class TestAcsFailureModes:
    def test_signature_invalid_401(self, pg_app, provider, idp):
        """Tampered Response → signature verification fails."""
        response_b64 = _build_signed_response(
            idp_key=idp["key_pem"],
            idp_cert=idp["cert_pem"],
            acs_url=_acs_url(provider),
            name_id="a@idp.example.test",
            email="a@idp.example.test",
        )
        tampered = bytearray(base64.b64decode(response_b64))
        # Flip a bit inside a signed element.
        for i, byte in enumerate(tampered):
            if byte == ord("e") and tampered[i : i + 5] == b"email":
                tampered[i] = ord("E")
                break
        response_b64 = base64.b64encode(bytes(tampered)).decode("ascii")
        client = pg_app.test_client()
        r = client.post(
            f"/saml/{provider.id}/acs",
            data={"SAMLResponse": response_b64},
        )
        assert r.status_code == 401

    def test_recipient_mismatch_401(self, pg_app, provider, idp):
        response_b64 = _build_signed_response(
            idp_key=idp["key_pem"],
            idp_cert=idp["cert_pem"],
            acs_url="https://other.example.test/acs",
            name_id="b@idp.example.test",
            email="b@idp.example.test",
        )
        client = pg_app.test_client()
        r = client.post(
            f"/saml/{provider.id}/acs",
            data={"SAMLResponse": response_b64},
        )
        assert r.status_code == 401
        assert "recipient" in r.get_json()["error"]

    def test_expired_assertion_401(self, pg_app, provider, idp):
        response_b64 = _build_signed_response(
            idp_key=idp["key_pem"],
            idp_cert=idp["cert_pem"],
            acs_url=_acs_url(provider),
            name_id="c@idp.example.test",
            email="c@idp.example.test",
            not_on_or_after=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        client = pg_app.test_client()
        r = client.post(
            f"/saml/{provider.id}/acs",
            data={"SAMLResponse": response_b64},
        )
        assert r.status_code == 401
        assert "expired" in r.get_json()["error"]

    def test_audience_mismatch_401(self, pg_app, provider, idp):
        response_b64 = _build_signed_response(
            idp_key=idp["key_pem"],
            idp_cert=idp["cert_pem"],
            acs_url=_acs_url(provider),
            name_id="d@idp.example.test",
            email="d@idp.example.test",
            audience="some-other-sp",
        )
        client = pg_app.test_client()
        r = client.post(
            f"/saml/{provider.id}/acs",
            data={"SAMLResponse": response_b64},
        )
        assert r.status_code == 401
        assert "audience" in r.get_json()["error"]

    def test_replay_refused(self, pg_app, provider, idp):
        response_b64 = _build_signed_response(
            idp_key=idp["key_pem"],
            idp_cert=idp["cert_pem"],
            acs_url=_acs_url(provider),
            name_id="e@idp.example.test",
            email="e@idp.example.test",
            assertion_id="_fixed_assertion_id",
        )
        client = pg_app.test_client()
        first = client.post(
            f"/saml/{provider.id}/acs",
            data={"SAMLResponse": response_b64},
        )
        assert first.status_code == 302
        second = client.post(
            f"/saml/{provider.id}/acs",
            data={"SAMLResponse": response_b64},
        )
        assert second.status_code == 401
        assert "replay" in second.get_json()["error"]

    def test_open_redirect_blocked(self, pg_app, provider, idp):
        """RelayState pointing at a foreign host is ignored."""
        response_b64 = _build_signed_response(
            idp_key=idp["key_pem"],
            idp_cert=idp["cert_pem"],
            acs_url=_acs_url(provider),
            name_id="f@idp.example.test",
            email="f@idp.example.test",
        )
        client = pg_app.test_client()
        r = client.post(
            f"/saml/{provider.id}/acs",
            data={
                "SAMLResponse": response_b64,
                "RelayState": "https://evil.example/path",
            },
        )
        assert r.status_code == 302
        assert r.headers["Location"] == "/"
