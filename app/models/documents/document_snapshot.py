"""Immutable snapshots of draft text for revision integrity.

Not a cryptographic signature, certified timestamp, or frozen PDF.
"""
from datetime import datetime
from app.extensions import db


class DocumentSnapshot(db.Model):
    __tablename__ = "document_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey("documents.id"), nullable=False, index=True)
    revision = db.Column(db.Integer, nullable=False)
    content_sha256 = db.Column(db.String(64), nullable=False)
    canonical_content = db.Column(db.Text, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("document_id", "revision", name="uq_document_snapshots_revision"),
    )
