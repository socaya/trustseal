"""Immutable platform attestations over signer review decisions.

Receipt is a signed *statement of platform records*, not a PDF signature.
"""
from datetime import datetime
from app.extensions import db


class ReviewReceipt(db.Model):
    __tablename__ = "review_receipts"
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    decision_id = db.Column(db.BigInteger, db.ForeignKey("signer_decisions.id"), nullable=False, unique=True)
    envelope_id = db.Column(db.Integer, db.ForeignKey("signing_envelopes.id"), nullable=False, index=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    payload = db.Column(db.JSON, nullable=False)
    algorithm = db.Column(db.String(16), nullable=False)
    key_id = db.Column(db.String(80), nullable=False)
    signature = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
