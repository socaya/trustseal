"""Reusable clause library.

A ``Clause`` is a tenant-scoped reusable piece of contract text. Each
clause has a lifecycle:

* ``draft`` — editable, unversioned snapshots accumulate below.
* ``approved`` — the current version is locked and ready for
  insertion into documents.
* ``archived`` — hidden from pickers; prior inclusions retain their
  snapshot.

Approval is gated by separation-of-duties: the user approving a
clause version must not be its author. The service layer records
every transition in the chained audit log.
"""
from datetime import datetime

from app.extensions import db


class Clause(db.Model):
    __tablename__ = "clauses"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(80), nullable=True)
    state = db.Column(
        db.String(20), nullable=False, default="draft", server_default="draft"
    )
    # FK declared only in the migration to avoid a chicken-and-egg
    # cycle with ``clause_versions`` during ``db.create_all``.
    current_version_id = db.Column(db.BigInteger, nullable=True)
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime, nullable=True)
    approved_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )
    archived_at = db.Column(db.DateTime, nullable=True)
    archived_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )

    versions = db.relationship(
        "ClauseVersion",
        back_populates="clause",
        cascade="all, delete-orphan",
        foreign_keys="ClauseVersion.clause_id",
    )

    __table_args__ = (
        db.CheckConstraint(
            "state IN ('draft','approved','archived')",
            name="ck_clause_state",
        ),
        db.UniqueConstraint(
            "organization_id", "name", name="uq_clause_org_name"
        ),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "name": self.name,
            "category": self.category,
            "state": self.state,
            "current_version_id": self.current_version_id,
            "created_by_id": self.created_by_id,
            "created_at": self.created_at.isoformat(),
            "approved_at": self.approved_at.isoformat()
            if self.approved_at
            else None,
            "archived_at": self.archived_at.isoformat()
            if self.archived_at
            else None,
        }


class ClauseVersion(db.Model):
    __tablename__ = "clause_versions"

    id = db.Column(db.BigInteger, primary_key=True)
    clause_id = db.Column(
        db.Integer, db.ForeignKey("clauses.id"), nullable=False, index=True
    )
    revision = db.Column(db.Integer, nullable=False)
    body = db.Column(db.Text, nullable=False, default="")
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime, nullable=True)
    approved_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )

    clause = db.relationship(
        "Clause", back_populates="versions", foreign_keys=[clause_id]
    )

    __table_args__ = (
        db.UniqueConstraint(
            "clause_id", "revision", name="uq_clause_version"
        ),
        db.CheckConstraint("revision > 0", name="ck_clause_version_revision"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "clause_id": self.clause_id,
            "revision": self.revision,
            "body": self.body,
            "created_by_id": self.created_by_id,
            "created_at": self.created_at.isoformat(),
            "approved_at": self.approved_at.isoformat()
            if self.approved_at
            else None,
            "approved_by_id": self.approved_by_id,
        }
