"""Per-participant conditional routing rules.

A rule is a JSON boolean predicate that must evaluate True before
its participant may be challenged. Rules layer on top of the routing
mode: sequential / parallel / quorum still apply, and the rule is an
additional gate.

Predicate shape (minimal, safe DSL — no eval, no arbitrary callables):

::

    {"op": "and", "args": [
        {"op": "eq", "lhs": {"ref": "participant.role"},
         "rhs": "witness"},
        {"op": "ge", "lhs": {"ref": "prior_decisions.acknowledged_count"},
         "rhs": 2}
    ]}

See :mod:`app.services.envelope_routing_rules` for the evaluator and
the full context schema.
"""
from datetime import datetime

from app.extensions import db


class EnvelopeRoutingRule(db.Model):
    __tablename__ = "envelope_routing_rules"

    id = db.Column(db.BigInteger, primary_key=True)
    envelope_id = db.Column(
        db.Integer,
        db.ForeignKey("signing_envelopes.id"),
        nullable=False,
        index=True,
    )
    participant_id = db.Column(
        db.Integer,
        db.ForeignKey("envelope_participants.id"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(80), nullable=False)
    predicate = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
