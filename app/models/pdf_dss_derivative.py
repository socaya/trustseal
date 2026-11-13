"""A separate immutable PDF derivative containing a Document Security Store.

This representation is *not* asserted to be PAdES-LT. It contains reviewed
certificate/status material in a post-signature incremental PDF revision.
"""
from datetime import datetime
from app.extensions import db


class PdfDssDerivative(db.Model):
    __tablename__ = "pdf_dss_derivatives"
    id = db.Column(db.BigInteger, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    retention_id = db.Column(db.BigInteger, db.ForeignKey("evidence_retentions.id"), nullable=False, index=True)
    dossier_id = db.Column(db.BigInteger, db.ForeignKey("validation_dossiers.id"), nullable=False, unique=True)
    operator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    source_sha256 = db.Column(db.String(64), nullable=False)
    dossier_sha256 = db.Column(db.String(64), nullable=False)
    object_key = db.Column(db.String(96), nullable=False, unique=True)
    output_sha256 = db.Column(db.String(64), nullable=False)
    output_size = db.Column(db.BigInteger, nullable=False)
    profile = db.Column(db.String(60), nullable=False, default="dss_evidence_only_not_pades_lt")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        db.CheckConstraint("output_size > 0", name="ck_pdf_dss_derivative_size"),
        db.CheckConstraint(
            "profile = 'dss_evidence_only_not_pades_lt'",
            name="ck_pdf_dss_derivative_profile",
        ),
    )
