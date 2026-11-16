"""Operator-defined label attached to a document (Phase Y1).

Mirror of :class:`EnvelopeLabel`. Labels are free-form tags scoped
to an organisation and intended for operator filtering on the
documents surface. Each label is unique per document; the
``organization_id`` column is duplicated so RLS can keep the row
tenant-scoped without joining back to ``documents``.
"""
from datetime import datetime

from app.extensions import db


class DocumentLabel(db.Model):
    __tablename__ = "document_labels"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(
        db.Integer,
        db.ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    label = db.Column(db.String(60), nullable=False)
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        db.UniqueConstraint(
            "document_id", "label", name="uq_document_label"
        ),
        db.CheckConstraint(
            "char_length(label) >= 1 AND char_length(label) <= 60",
            name="ck_document_label_length",
        ),
        db.Index("ix_document_labels_org_label", "organization_id", "label"),
    )
