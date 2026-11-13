"""One immutable platform-sealed PDF per prepared signing envelope.

The CMS signer is the platform certificate holder, NOT each human reviewer.
"""
from datetime import datetime
from app.extensions import db


class FinalizedPdf(db.Model):
    __tablename__ = "finalized_pdfs"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    envelope_id = db.Column(db.Integer, db.ForeignKey("signing_envelopes.id"),
                            nullable=False, unique=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"),
                                nullable=False, index=True)
    source_blob_id = db.Column(db.Integer, db.ForeignKey("document_blobs.id"),
                               nullable=False)
    source_sha256 = db.Column(db.String(64), nullable=False)
    object_key = db.Column(db.String(96), nullable=False, unique=True)
    output_sha256 = db.Column(db.String(64), nullable=False)
    output_size = db.Column(db.BigInteger, nullable=False)
    certificate_sha256 = db.Column(db.String(64), nullable=False)
    signature_field = db.Column(db.String(100), nullable=False)
    profile = db.Column(db.String(32), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.CheckConstraint("output_size > 0", name="ck_finalized_pdf_size"),
    )
