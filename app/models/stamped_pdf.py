"""Immutable, separately signed PDF derived from an approved stamp attestation.

The original platform-signed PDF is never modified. The derivative is built
from the *unsigned* frozen source and signed after its visible impression.
"""
from datetime import datetime
from app.extensions import db


class StampedPdf(db.Model):
    __tablename__ = "stamped_pdfs"

    id = db.Column(db.BigInteger, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    stamp_attestation_id = db.Column(
        db.BigInteger, db.ForeignKey("stamp_attestations.id"), nullable=False, unique=True
    )
    design_version_id = db.Column(db.BigInteger, db.ForeignKey("stamp_design_versions.id"))
    design_sha256 = db.Column(db.String(64))
    source_finalized_pdf_id = db.Column(
        db.BigInteger, db.ForeignKey("finalized_pdfs.id"), nullable=False
    )
    source_finalized_sha256 = db.Column(db.String(64), nullable=False)
    original_document_sha256 = db.Column(db.String(64), nullable=False)
    stamp_evidence_sha256 = db.Column(db.String(64), nullable=False)
    signed_evidence_sha256 = db.Column(db.String(64), nullable=False)
    object_key = db.Column(db.String(96), nullable=False, unique=True)
    output_sha256 = db.Column(db.String(64), nullable=False)
    output_size = db.Column(db.BigInteger, nullable=False)
    certificate_sha256 = db.Column(db.String(64), nullable=False)
    page_number = db.Column(db.Integer, nullable=False)
    x_pt = db.Column(db.Integer, nullable=False)
    y_pt = db.Column(db.Integer, nullable=False)
    issued_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        db.CheckConstraint("output_size > 0", name="ck_stamped_pdf_output_size"),
        db.CheckConstraint("page_number >= 1", name="ck_stamped_pdf_page"),
        db.CheckConstraint("x_pt >= 0 AND y_pt >= 0", name="ck_stamped_pdf_position"),
    )
