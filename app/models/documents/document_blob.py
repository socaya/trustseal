"""Manifest for scanned, private, append-only document file objects.

This is a staged private-file foundation, not a signing evidence package.
Object bytes must be backed up separately and stored outside the web root.
"""
from datetime import datetime
from app.extensions import db


class DocumentBlob(db.Model):
    __tablename__ = "document_blobs"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey("documents.id"), nullable=False, index=True)
    revision = db.Column(db.Integer, nullable=False)
    object_key = db.Column(db.String(96), nullable=False, unique=True)
    file_name = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(100), nullable=False)
    file_size = db.Column(db.BigInteger, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    scanner = db.Column(db.String(32), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("document_id", "revision", name="uq_document_blobs_revision"),
        db.CheckConstraint("file_size > 0", name="ck_document_blobs_nonempty"),
    )
