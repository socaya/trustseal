"""Bulk document ingest tracking.

One ``BulkIngestBatch`` groups N ``BulkIngestItem`` rows, one per
uploaded file. The response of the bulk endpoint returns the batch
plus every item so clients can retry failed files without re-sending
successful ones.

The batch is durable on purpose: the client can disconnect halfway
through the upload and still retrieve a record of which files landed
by polling the batch resource.
"""
from datetime import datetime

from app.extensions import db


class BulkIngestBatch(db.Model):
    __tablename__ = "bulk_ingest_batches"

    id = db.Column(db.BigInteger, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    item_count = db.Column(db.Integer, nullable=False, default=0)
    success_count = db.Column(db.Integer, nullable=False, default=0)
    failure_count = db.Column(db.Integer, nullable=False, default=0)

    items = db.relationship(
        "BulkIngestItem", back_populates="batch", cascade="all, delete-orphan"
    )


class BulkIngestItem(db.Model):
    __tablename__ = "bulk_ingest_items"

    id = db.Column(db.BigInteger, primary_key=True)
    batch_id = db.Column(
        db.BigInteger,
        db.ForeignKey("bulk_ingest_batches.id"),
        nullable=False,
        index=True,
    )
    filename = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    document_id = db.Column(
        db.Integer, db.ForeignKey("documents.id"), nullable=True
    )
    blob_id = db.Column(
        db.Integer, db.ForeignKey("document_blobs.id"), nullable=True
    )
    error_code = db.Column(db.String(60), nullable=True)
    error_message = db.Column(db.String(400), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    batch = db.relationship("BulkIngestBatch", back_populates="items")

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending','succeeded','failed')",
            name="ck_bulk_ingest_item_status",
        ),
    )
