"""TRUSTSEAL proprietary document ("TrustSeal Document", .tsd).

A .tsd row stores an encrypted content payload plus the metadata needed
to list, open, and audit the document without decrypting it.

Encryption: Fernet (AES-128-CBC + HMAC-SHA256), key derived per tenant
from ``SECRET_KEY``. See :mod:`app.services.tsd_format` for the
canonical container spec and crypto choices.

Export policy
    ``pdf_allowed``     — operator can render the TSD to PDF for
                          signing / printing. The raw .tsd downloadable
                          stays encrypted.
    ``encrypted_only``  — no plaintext leaves TrustSeal. Only encrypted
                          .tsd bytes can be downloaded.
"""
from datetime import datetime

from app.extensions import db


EXPORT_POLICIES = ("pdf_allowed", "encrypted_only")
TSD_STATUSES = ("draft", "finalized", "archived")


class TSDocument(db.Model):
    __tablename__ = "ts_documents"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )

    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(1000))
    tags = db.Column(db.String(500))

    # Per-document policy chosen at creation (admin-editable on edit).
    export_policy = db.Column(
        db.String(24), nullable=False, default="pdf_allowed"
    )
    status = db.Column(db.String(24), nullable=False, default="draft")

    # Encrypted content payload — this is the Fernet ciphertext over the
    # JSON content envelope (see :func:`tsd_format.pack_content`).
    ciphertext = db.Column(db.LargeBinary, nullable=False)
    ciphertext_sha256 = db.Column(db.String(64), nullable=False)
    plaintext_bytes = db.Column(db.Integer, nullable=False, default=0)
    content_mime = db.Column(
        db.String(80), nullable=False,
        default="application/vnd.trustseal.doc+json",
    )

    # Optimistic concurrency token. Every PUT bumps this and the API
    # requires ``If-Match: <version>`` so two editors can't silently
    # clobber each other.
    version = db.Column(
        db.Integer, nullable=False, default=1, server_default=db.text("1")
    )

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at = db.Column(db.DateTime, index=True)

    __table_args__ = (
        db.CheckConstraint(
            "export_policy IN ('pdf_allowed','encrypted_only')",
            name="ck_tsd_export_policy",
        ),
        db.CheckConstraint(
            "status IN ('draft','finalized','archived')",
            name="ck_tsd_status",
        ),
        db.CheckConstraint("version > 0", name="ck_tsd_version_positive"),
    )

    def to_dict(self, *, include_content: bool = False) -> dict:
        row = {
            "id": self.id,
            "organization_id": self.organization_id,
            "created_by_id": self.created_by_id,
            "title": self.title,
            "description": self.description,
            "tags": self.tags,
            "export_policy": self.export_policy,
            "status": self.status,
            "content_mime": self.content_mime,
            "ciphertext_sha256": self.ciphertext_sha256,
            "plaintext_bytes": self.plaintext_bytes,
            "version": self.version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_content:
            from app.services.tsd_format import decrypt_content_envelope

            row["content"] = decrypt_content_envelope(
                self.ciphertext, organization_id=self.organization_id
            )
        return row
