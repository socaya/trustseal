"""Time-bound authority delegation.

A delegation lets ``delegate_id`` act with the scope of ``delegator_id``
for a bounded window. Scopes are named strings matched by the policy
helper; both parties remain in audit history.

Design:

* ``scope`` is a simple dotted string such as ``"stamp.approve"`` or
  ``"envelope.finalize"``. Callers compare scopes exactly — no
  substring match. A ``"*"`` wildcard delegates every scope, used
  for short out-of-office transfers.
* ``resource_type`` + ``resource_id`` optionally narrow a delegation
  to one specific record. NULL means tenant-wide for that scope.
* Validity window ``starts_at`` ... ``expires_at`` is inclusive on
  ``starts_at`` and exclusive on ``expires_at``.
* ``revoked_at`` is independent of ``expires_at`` — a delegator can
  cancel the delegation early.
* Append-only on the production trigger side (not installed by
  ``create_all`` in unit tests; integration conftest installs it).
"""
from datetime import datetime

from app.extensions import db


class Delegation(db.Model):
    __tablename__ = "delegations"

    id = db.Column(db.BigInteger, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"),
        nullable=False, index=True,
    )
    delegator_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    delegate_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    scope = db.Column(db.String(80), nullable=False)
    resource_type = db.Column(db.String(60), nullable=True)
    resource_id = db.Column(db.BigInteger, nullable=True)
    reason = db.Column(db.String(255), nullable=True)
    starts_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    granted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    granted_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    revoked_at = db.Column(db.DateTime, nullable=True)
    revoked_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )
    revoke_reason = db.Column(db.String(255), nullable=True)

    __table_args__ = (
        db.CheckConstraint(
            "expires_at > starts_at", name="ck_delegations_window"
        ),
    )
