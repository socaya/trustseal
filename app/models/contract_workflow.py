"""Standard Contract Deal-Closing Workflow state for TrustSeal Documents.

Tracks the end-to-end enterprise contract lifecycle up to closing a deal
and executing the agreement with TrustSeal (Draft -> Review -> Approval ->
Agreement Signing with TS -> Deal Closed -> Archived/Void) while keeping
``ts_documents.status`` strictly within its canonical DB check constraint
(``draft``, ``finalized``, ``archived``).
"""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import inspect

from app.extensions import db


WORKFLOW_STAGES = (
    ("draft",     "Draft"),
    ("review",    "Pending Review"),
    ("approval",  "Pending Approval"),
    ("signature", "Agreement Signing (TS)"),
    ("signed",    "Deal Closed"),
    ("closed",    "Archived / Void"),
)

STAGE_LABELS = dict(WORKFLOW_STAGES)


class ContractWorkflow(db.Model):
    __tablename__ = "contract_workflows"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True
    )
    document_id = db.Column(
        db.Integer, db.ForeignKey("ts_documents.id"), nullable=False, unique=True, index=True
    )
    stage = db.Column(db.String(24), nullable=False, default="draft")

    counterparty_name = db.Column(db.String(200), nullable=True)
    deal_value = db.Column(db.String(64), nullable=True)
    currency = db.Column(db.String(12), nullable=False, default="USD")
    effective_date = db.Column(db.String(32), nullable=True)
    governing_law = db.Column(db.String(120), nullable=True)
    letterhead_id = db.Column(db.Integer, nullable=True)
    stamp_id = db.Column(db.Integer, nullable=True)

    # JSON blobs for flexible checklist, signatories, and chronological audit trail
    checklist_json = db.Column(db.JSON, nullable=False, default=dict)
    signers_json = db.Column(db.JSON, nullable=False, default=list)
    events_json = db.Column(db.JSON, nullable=False, default=list)

    closed_at = db.Column(db.DateTime, nullable=True)
    execution_sha256 = db.Column(db.String(64), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "stage": self.stage,
            "stage_label": STAGE_LABELS.get(self.stage, "Draft"),
            "counterparty_name": self.counterparty_name or "",
            "deal_value": self.deal_value or "",
            "currency": self.currency or "USD",
            "effective_date": self.effective_date or "",
            "governing_law": self.governing_law or "",
            "letterhead_id": self.letterhead_id,
            "stamp_id": self.stamp_id,
            "checklist": self.checklist_json or {},
            "signers": self.signers_json or [],
            "events": self.events_json or [],
            "closed_at": self.closed_at.strftime("%Y-%m-%d %H:%M UTC") if self.closed_at else "",
            "execution_sha256": self.execution_sha256 or "",
        }


_TABLE_READY = False


def ensure_contract_workflow_table() -> None:
    """Create ``contract_workflows`` table on first use if not yet migrated."""
    global _TABLE_READY
    if _TABLE_READY:
        return
    try:
        insp = inspect(db.engine)
        if not insp.has_table(ContractWorkflow.__tablename__):
            ContractWorkflow.__table__.create(db.engine, checkfirst=True)
        _TABLE_READY = True
    except Exception:
        pass
