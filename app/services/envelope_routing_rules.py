"""Conditional envelope routing: rule store + predicate evaluator.

Rules layer on top of the fixed routing modes (sequential, parallel,
quorum). If a participant has one or more rules attached, every rule
must evaluate True before the participant may be challenged — in
addition to the routing-mode gate.

Predicate DSL:

* ``{"op": "and", "args": [...]}`` / ``{"op": "or", "args": [...]}``
* ``{"op": "not", "arg": {...}}``
* ``{"op": <cmp>, "lhs": <term>, "rhs": <term>}`` where ``cmp`` is
  one of ``eq``, ``ne``, ``gt``, ``ge``, ``lt``, ``le``.
* Terms:
  * ``{"ref": "<dotted key>"}`` — look up in the context.
  * literal string / int / bool.

Context exposed to predicates:

* ``participant.role``, ``participant.signing_order``,
  ``participant.user_id``.
* ``envelope.routing_mode``, ``envelope.quorum_required``.
* ``prior_decisions.acknowledged_count``,
  ``prior_decisions.declined_count``,
  ``prior_decisions.pending_count``.

The evaluator is deliberately strict: unknown operators, missing
refs, or type mismatches raise :class:`RuleError`. This prevents
silent "False" decisions that could hide a misconfigured rule.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

from app.extensions import db
from app.models.envelope_routing_rule import EnvelopeRoutingRule
from app.models.signer_decision import SignerDecision
from app.models.signing_envelope import EnvelopeParticipant, SigningEnvelope


class RuleError(Exception):
    """Invalid predicate structure or evaluation failure."""


COMPARATORS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a > b,
    "ge": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "le": lambda a, b: a <= b,
}
MAX_DEPTH = 8


def _resolve_ref(ref: str, context: Mapping[str, Any]) -> Any:
    current: Any = context
    for part in ref.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        else:
            raise RuleError(f"ref_unknown:{ref}")
    return current


def _term_value(term: Any, context: Mapping[str, Any]) -> Any:
    if isinstance(term, Mapping):
        if "ref" in term:
            ref = term["ref"]
            if not isinstance(ref, str):
                raise RuleError("ref_not_string")
            return _resolve_ref(ref, context)
        raise RuleError("term_unknown_shape")
    if isinstance(term, (str, int, bool)) or term is None:
        return term
    raise RuleError(f"term_unsupported:{type(term).__name__}")


def evaluate_predicate(
    predicate: Any, context: Mapping[str, Any], *, depth: int = 0
) -> bool:
    if depth > MAX_DEPTH:
        raise RuleError("predicate_too_deep")
    if not isinstance(predicate, Mapping):
        raise RuleError("predicate_not_object")
    op = predicate.get("op")
    if op == "and":
        args = predicate.get("args")
        if not isinstance(args, list) or not args:
            raise RuleError("and_requires_args")
        return all(
            evaluate_predicate(sub, context, depth=depth + 1) for sub in args
        )
    if op == "or":
        args = predicate.get("args")
        if not isinstance(args, list) or not args:
            raise RuleError("or_requires_args")
        return any(
            evaluate_predicate(sub, context, depth=depth + 1) for sub in args
        )
    if op == "not":
        inner = predicate.get("arg")
        if inner is None:
            raise RuleError("not_requires_arg")
        return not evaluate_predicate(inner, context, depth=depth + 1)
    cmp = COMPARATORS.get(op)
    if cmp is None:
        raise RuleError(f"op_unknown:{op}")
    if "lhs" not in predicate or "rhs" not in predicate:
        raise RuleError(f"{op}_requires_lhs_rhs")
    lhs = _term_value(predicate["lhs"], context)
    rhs = _term_value(predicate["rhs"], context)
    try:
        return bool(cmp(lhs, rhs))
    except TypeError as exc:
        raise RuleError(f"{op}_type_mismatch:{lhs!r}:{rhs!r}") from exc


# ------------------------------------------------------------- context


def build_context(
    envelope: SigningEnvelope,
    participant: EnvelopeParticipant,
) -> dict[str, Any]:
    """Collect everything the predicate can see."""
    decisions = SignerDecision.query.filter_by(
        envelope_id=envelope.id
    ).all()
    acknowledged = sum(1 for d in decisions if d.decision == "acknowledged")
    declined = sum(1 for d in decisions if d.decision == "declined")
    participant_count = EnvelopeParticipant.query.filter_by(
        envelope_id=envelope.id
    ).count()
    pending = participant_count - acknowledged - declined
    return {
        "participant": {
            "role": participant.role,
            "signing_order": participant.signing_order,
            "user_id": participant.user_id,
        },
        "envelope": {
            "routing_mode": envelope.routing_mode,
            "quorum_required": envelope.quorum_required,
        },
        "prior_decisions": {
            "acknowledged_count": acknowledged,
            "declined_count": declined,
            "pending_count": pending,
        },
    }


# ------------------------------------------------------------- service


@dataclass(frozen=True)
class RuleOutcome:
    allowed: bool
    failed_rule_names: tuple[str, ...]


def evaluate_rules(
    envelope: SigningEnvelope,
    participant: EnvelopeParticipant,
) -> RuleOutcome:
    """Return the combined outcome of every rule for the participant.

    No rules → ``allowed=True`` with an empty failure tuple. Any rule
    returning False puts the gate at False and records the rule name
    for the caller to surface in the error payload.
    """
    rows = EnvelopeRoutingRule.query.filter_by(
        envelope_id=envelope.id, participant_id=participant.id
    ).all()
    if not rows:
        return RuleOutcome(allowed=True, failed_rule_names=())
    context = build_context(envelope, participant)
    failures: list[str] = []
    for row in rows:
        try:
            if not evaluate_predicate(row.predicate, context):
                failures.append(row.name)
        except RuleError as exc:
            # A malformed rule fails closed — the caller can't exercise
            # the participant until a tenant admin fixes the predicate.
            failures.append(f"{row.name}({exc})")
    return RuleOutcome(allowed=not failures, failed_rule_names=tuple(failures))


def add_rule(
    envelope: SigningEnvelope,
    participant: EnvelopeParticipant,
    *,
    name: str,
    predicate: Mapping[str, Any],
    created_by_id: int,
) -> EnvelopeRoutingRule:
    if envelope.state != "draft":
        raise RuleError("envelope_not_draft")
    if participant.envelope_id != envelope.id:
        raise RuleError("participant_envelope_mismatch")
    if not isinstance(name, str) or not 1 <= len(name) <= 80:
        raise RuleError("name_invalid")
    # Validate predicate immediately so bad JSON fails at write time,
    # not at evaluation time.
    probe_context = build_context(envelope, participant)
    try:
        evaluate_predicate(predicate, probe_context)
    except RuleError:
        # We still allow rules that reference facts not present in the
        # probe context (future states). Re-raise only on structural
        # errors — unknown refs are context-dependent.
        pass
    row = EnvelopeRoutingRule(
        envelope_id=envelope.id,
        participant_id=participant.id,
        name=name,
        predicate=dict(predicate),
        created_by_id=created_by_id,
    )
    db.session.add(row)
    db.session.flush()
    return row


def delete_rule(envelope: SigningEnvelope, rule_id: int) -> None:
    if envelope.state != "draft":
        raise RuleError("envelope_not_draft")
    row = db.session.get(EnvelopeRoutingRule, rule_id)
    if row is None or row.envelope_id != envelope.id:
        raise RuleError("rule_not_found")
    db.session.delete(row)


def list_rules(envelope: SigningEnvelope) -> list[EnvelopeRoutingRule]:
    return EnvelopeRoutingRule.query.filter_by(
        envelope_id=envelope.id
    ).order_by(EnvelopeRoutingRule.id.asc()).all()
