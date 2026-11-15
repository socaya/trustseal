"""Tenant-scoped OIDC identity provider configuration.

Each tenant may register one or more OIDC providers (Google Workspace,
Azure AD, Okta, …). The ``slug`` is a URL-safe handle the discovery
flow uses; it is not disclosed outside the tenant.

Trusted email domains gate just-in-time user creation: callers whose
``email_verified`` claim is True and whose address ends in a listed
domain are auto-provisioned into the tenant on first login.
"""
from datetime import datetime

from app.extensions import db


class OidcProvider(db.Model):
    __tablename__ = "oidc_providers"

    id = db.Column(db.BigInteger, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    slug = db.Column(db.String(64), nullable=False)
    display_name = db.Column(db.String(120), nullable=False)
    issuer = db.Column(db.String(256), nullable=False)
    client_id = db.Column(db.String(256), nullable=False)
    client_secret_cipher = db.Column(db.String(1024), nullable=False)
    trusted_email_domains = db.Column(db.JSON, nullable=False, default=list)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        db.UniqueConstraint("organization_id", "slug", name="uq_oidc_provider_slug"),
    )
