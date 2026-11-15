"""Signed, append-only anchors that pin the audit chain to an external key.

Each anchor captures the current SecurityEvent chain tip for a tenant
plus the id of the event it anchors against, signs that payload with
the configured Ed25519 checkpoint key, and stores the detached
signature. Anchors are append-only: the database refuses mutation
through a trigger-free convention — the service only ever inserts.

The companion verifier in :mod:`app.services.audit_chain` walks every
anchor for a tenant, re-derives the chain tip at ``anchor_event_id``
using the chained-hash integrity probe, and compares. A DB-level
rewrite that preserves the internal chain but changes an event hash
will produce a mismatch at every anchor that pointed at a
re-hashed row.
"""
from datetime import datetime

from app.extensions import db


class AuditChainAnchor(db.Model):
    __tablename__ = "audit_chain_anchors"

    id = db.Column(db.BigInteger, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), index=True
    )
    anchor_event_id = db.Column(db.BigInteger)
    chain_tip_hash = db.Column(db.String(64), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    algorithm = db.Column(db.String(16), nullable=False)
    key_id = db.Column(db.String(80), nullable=False)
    signature = db.Column(db.Text, nullable=False)
    operator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
