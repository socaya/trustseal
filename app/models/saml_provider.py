"""Per-organization SAML 2.0 Identity Provider configuration.

Each row defines one IdP that the Service Provider will accept
assertions from. The X.509 certificate is stored as PEM; the SSO URL
is where the AuthnRequest is sent; the attribute mapping tells the
JIT provisioner which SAML attribute carries the user's email,
display name, etc.

Replay protection is handled at a separate table
(:class:`app.models.saml_consumed_assertion.SamlConsumedAssertion`)
so this row stays static once configured.
"""
from datetime import datetime

from app.extensions import db


class SamlProvider(db.Model):
    __tablename__ = "saml_providers"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    display_name = db.Column(db.String(120), nullable=False)
    entity_id = db.Column(db.String(255), nullable=False)
    sso_url = db.Column(db.String(500), nullable=False)
    x509_cert_pem = db.Column(db.Text, nullable=False)
    audience = db.Column(db.String(255), nullable=False)
    attribute_mapping = db.Column(db.JSON, nullable=False, default=dict)
    # Optional SP signing credentials. When both are set the service
    # signs every outbound AuthnRequest per SAML HTTP-Redirect binding
    # §3.4.4.1 so IdPs that require ``AuthnRequestsSigned`` accept us.
    sp_signing_private_key_pem = db.Column(db.Text, nullable=True)
    sp_signing_cert_pem = db.Column(db.Text, nullable=True)
    is_active = db.Column(
        db.Boolean, nullable=False, default=True, server_default=db.text("true")
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint(
            "organization_id", "entity_id", name="uq_saml_provider_entity"
        ),
    )


class SamlConsumedAssertion(db.Model):
    """Replay-protection marker for consumed SAML assertion IDs.

    A fresh AuthnResponse's assertion ID is recorded here when the
    response is accepted. A later response with the same ID is
    refused, defeating replay attacks.
    """

    __tablename__ = "saml_consumed_assertions"

    id = db.Column(db.BigInteger, primary_key=True)
    provider_id = db.Column(
        db.Integer,
        db.ForeignKey("saml_providers.id"),
        nullable=False,
        index=True,
    )
    assertion_id = db.Column(db.String(255), nullable=False)
    consumed_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )
    not_on_or_after = db.Column(db.DateTime, nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "provider_id", "assertion_id",
            name="uq_saml_consumed_assertion",
        ),
    )
