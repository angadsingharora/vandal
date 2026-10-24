"""R2: the gate (Blue core). Runs compiled Checks at each stage; the most restrictive match wins.

The gate only sees deterministic facts. Evidence-gated holds (`Check.require`) land in R6.

Fail closed: if a check needs a fact the gate can't compute, the check fires anyway, at least as
a hold, so a gap in facts.py can never let an action through. The verdict names the missing facts.
"""

from __future__ import annotations

from typing import Any

from vandal.contracts.controls import DECISION_ORDER, Check, Condition, Stage
from vandal.contracts.interfaces import Action
from vandal.contracts.verdicts import Verdict
from vandal.twin.facts import facts
from vandal.twin.state import State

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


class Gate:
    def __init__(self, checks: list[Check]) -> None:
        self.checks = list(checks)

    def check(self, state: State, action: Action, stage: Stage) -> Verdict:
        f, cites = facts(state, action)
        fired: list[str] = []
        decisions: list[str] = []
        missing: set[str] = set()
        for c in self.checks:
            if c.stage != stage:
                continue
            gaps = {cond.fact for cond in c.when.all if cond.fact not in f}
            if gaps:
                missing |= gaps
                fired.append(c.id)
                decisions.append(max(c.action, "hold", key=DECISION_ORDER.__getitem__))
            elif all(holds(cond, f) for cond in c.when.all):
                fired.append(c.id)
                decisions.append(c.action)
        if missing:
            f = {**f, "gate.missing_facts": sorted(missing)}
        decision = max(decisions, key=DECISION_ORDER.__getitem__, default="allow")
        return Verdict(decision=decision, fired=fired, facts=f, cites=cites)
