"""Time-bound break-glass access grants.

A break-glass grant is a short-lived authorisation for an operator
to perform administrative actions inside a tenant they would not
otherwise have access to. The grant carries:

* the ``operator_id`` of the person who will act under it,
* the ``granted_by_id`` of the admin who authorised the grant,
* a ``scope`` string naming the kind of action permitted,
* an ``expires_at`` wall clock,
* a ``use_count`` that monotonically increments on each use,
* a ``revoked_at`` field so an admin can withdraw an unused grant.

Two independent operators are required to issue a grant (encoded in
the CLI). The service refuses ``granted_by_id == operator_id``.
"""
from datetime import datetime

from app.extensions import db


class BreakGlassGrant(db.Model):
    __tablename__ = "break_glass_grants"

    id = db.Column(db.BigInteger, primary_key=True)
    operator_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    granted_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=True
    )
    scope = db.Column(db.String(80), nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    granted_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )
    expires_at = db.Column(db.DateTime, nullable=False)
    use_count = db.Column(
        db.Integer, nullable=False, default=0, server_default=db.text("0")
    )
    last_used_at = db.Column(db.DateTime, nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=True)
    revoked_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )
    revoke_reason = db.Column(db.String(500), nullable=True)
