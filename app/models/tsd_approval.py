"""TSD approval workflow — basic sequential/parallel approvers
(DOC-083–DOC-095 reduced to a shippable v1).

A TSD can have an approval chain attached. Each approver has a position
in the chain (``order_index``). When ``order_index`` matches across
multiple approvers, they act in parallel at that step.

Approver decisions:
    * ``pending``
    * ``approved``
    * ``rejected``
    * ``changes_requested``

Workflow states derived at read time:
    * all approvers pending       → "awaiting_first"
    * one or more approved, no rejections → "in_progress"
    * any rejection                → "rejected"
    * any changes_requested        → "changes_requested"
    * all approved                 → "approved"

The engine enforces that an approver can only decide when prior steps
have completed (sequential enforcement at the ``order_index`` level).
"""
from datetime import datetime

from app.extensions import db


APPROVAL_DECISIONS = ("pending", "approved", "rejected", "changes_requested")


class TSDApproval(db.Model):
    __tablename__ = "ts_document_approvals"

    id = db.Column(db.Integer, primary_key=True)
    tsd_id = db.Column(
        db.Integer, db.ForeignKey("ts_documents.id"),
        nullable=False, index=True,
    )
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"),
        nullable=False, index=True,
    )
    approver_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False,
    )
    order_index = db.Column(db.Integer, nullable=False, default=0)

    status = db.Column(db.String(24), nullable=False, default="pending")
    note = db.Column(db.String(1000))

    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    decided_at = db.Column(db.DateTime)

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending','approved','rejected','changes_requested')",
            name="ck_tsd_approval_status",
        ),
        db.UniqueConstraint(
            "tsd_id", "approver_id",
            name="uq_tsd_approval_doc_approver",
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tsd_id": self.tsd_id,
            "approver_id": self.approver_id,
            "order_index": self.order_index,
            "status": self.status,
            "note": self.note,
            "created_by_id": self.created_by_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
        }
