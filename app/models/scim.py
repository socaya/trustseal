"""SCIM 2.0 service-account tokens.

Each tenant may issue one or more bearer tokens for provisioning
integrations (Okta, Azure AD, OneLogin, …). The raw token is only
returned once at creation; the database stores a salted SHA-256
digest so a DB compromise does not leak the token itself.
"""
from datetime import datetime

from app.extensions import db


class ScimServiceAccount(db.Model):
    __tablename__ = "scim_service_accounts"

    id = db.Column(db.BigInteger, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    display_name = db.Column(db.String(120), nullable=False)
    token_hash = db.Column(db.String(128), nullable=False, unique=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_used_at = db.Column(db.DateTime)
    # Lifecycle extensions (Phase L1). Nullable ``expires_at`` keeps
    # the pre-rotation semantics (never expires) while allowing new
    # tokens to carry a bounded lifetime.
    expires_at = db.Column(db.DateTime, nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=True)
    revoked_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )
    revoke_reason = db.Column(db.String(200), nullable=True)
    # ``rotated_from_id`` links a freshly-rotated account to the
    # superseded one. Rotation preserves history instead of deleting.
    rotated_from_id = db.Column(
        db.BigInteger,
        db.ForeignKey(
            "scim_service_accounts.id",
            use_alter=True,
            name="fk_scim_rotated_from",
        ),
        nullable=True,
    )
