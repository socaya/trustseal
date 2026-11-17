"""Append-only snapshot of each TSD ciphertext version.

When ``PUT /api/tsd/<id>`` changes content_html, the previous
ciphertext + hash + size are snapshotted into this table **before**
the parent row is rewritten. Prior versions are never mutated and
never deleted (soft or hard) — restores produce a new current version
that points back at the restored snapshot.
"""
from datetime import datetime

from app.extensions import db


class TSDocumentVersion(db.Model):
    __tablename__ = "ts_document_versions"

    id = db.Column(db.Integer, primary_key=True)
    tsd_id = db.Column(
        db.Integer, db.ForeignKey("ts_documents.id"),
        nullable=False, index=True,
    )
    version = db.Column(db.Integer, nullable=False)
    ciphertext = db.Column(db.LargeBinary, nullable=False)
    ciphertext_sha256 = db.Column(db.String(64), nullable=False)
    plaintext_bytes = db.Column(db.Integer, nullable=False, default=0)
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    change_note = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("tsd_id", "version", name="uq_tsd_version"),
    )
