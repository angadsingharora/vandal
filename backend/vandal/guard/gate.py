"""R2: the gate (Blue core). Runs compiled Checks at each stage; the most restrictive match wins.

The gate only sees deterministic facts. A hold whose Check has a `require` clause clears only
when the required evidence is on record (twin/evidence.satisfying); the verdict then names the
evidence in `gate.cleared_evidence`, or says what it would take in `gate.requires`.

Fail closed: if a check needs a fact the gate can't compute, the check fires anyway, at least as
a hold, so a gap in facts.py can never let an action through. The verdict names the missing facts.
"""

from __future__ import annotations

from typing import Any

from vandal.contracts.controls import DECISION_ORDER, Check, Condition, Stage
from vandal.contracts.interfaces import Action
from vandal.contracts.verdicts import Verdict
from vandal.guard.chain import chain_facts
from vandal.guard.sod import sod_checks
from vandal.twin.evidence import satisfying
from vandal.twin.facts import facts
from vandal.twin.state import State, construct

_MISSING = object()


def holds(cond: Condition, f: dict[str, Any]) -> bool:
    """Evaluate one condition. The caller handles missing facts (fail closed)."""
    value = f.get(cond.fact, _MISSING)
    if value is _MISSING:
        raise KeyError(cond.fact)
    match cond.op:
        case "eq":
            return value == cond.value
        case "ne":
            return value != cond.value
        case "lt":
            return value < cond.value
        case "lte":
            return value <= cond.value
        case "gt":
            return value > cond.value
        case "gte":
            return value >= cond.value
        case "in":
            return value in cond.value
        case "not_in":
            return value not in cond.value
        case "changed_since":
            raise NotImplementedError("changed_since lands with T1 in R6")
    raise ValueError(f"unknown op {cond.op!r}")


def _cleared_by(state: State, f: dict[str, Any], check: Check) -> list[str]:
    """Evidence that clears an evidence-gated hold. Only recorded evidence counts: what anyone
    says in a conversation never does."""
    subject = f.get("change.id")
    if not subject or check.require is None:
        return []
    return satisfying(state, subject, check.require)


class Gate:
    def __init__(self, checks: list[Check], sod: bool = True) -> None:
        """`checks` is the policy (v0 plus its controls). Blue's segregation-of-duties checks
        (guard/sod.py) come first and are always on unless `sod=False`."""
        from vandal.twin.flows import TOOLS

        always = sod_checks({name: spec.stage for name, spec in TOOLS.items()}) if sod else []
        self.checks = always + list(checks)

    def check(self, state: State, action: Action, stage: Stage) -> Verdict:
        f, cites = facts(state, action)
        fired: list[str] = []
        decisions: list[str] = []
        missing: set[str] = set()
        requires: list[dict] = []  # holds that evidence could clear: what it would take
        cleared: list[str] = []
        cleared_evidence: set[str] = set()
        for c in self.checks:
            if c.stage != stage:
                continue
            gaps = {cond.fact for cond in c.when.all if cond.fact not in f}
            if gaps:
                missing |= gaps
                fired.append(c.id)
                decisions.append(max(c.action, "hold", key=DECISION_ORDER.__getitem__))
            elif all(holds(cond, f) for cond in c.when.all):
                if c.action == "hold" and c.require is not None:
                    evidence = _cleared_by(state, f, c)
                    if evidence:
                        cleared.append(c.id)
                        cleared_evidence |= set(evidence)
                        continue
                    requires.append({"check": c.id, **c.require.model_dump()})
                fired.append(c.id)
                decisions.append(c.action)
        if stage == "pre_execute":
            f = {**f, **chain_facts(f)}  # B2: the chain as Blue sees it, on every execute
        if missing:
            f = {**f, "gate.missing_facts": sorted(missing)}
        if requires:
            f = {**f, "gate.requires": requires}
        if cleared:
            f = {**f, "gate.cleared": cleared, "gate.cleared_evidence": sorted(cleared_evidence)}
            cites = cites + sorted(cleared_evidence)
        decision = max(decisions, key=DECISION_ORDER.__getitem__, default="allow")
        fields = {"decision": decision, "fired": fired, "facts": f, "cites": cites}
        return construct(Verdict, fields)  # every field built above; skip validation
