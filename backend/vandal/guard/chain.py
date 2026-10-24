"""B2: the authorization chain at runtime.

Two things, both Blue's:

  pre_execute  every verdict on `payments.execute` carries the chain as Blue sees it: what was
               approved, what is about to be paid, and whether the payee is verified. Whether
               a mismatch *holds* is up to the policy (T2, T1); the facts are always there, so
               a verdict can always say why.
  monitor      after every World step, Blue runs the invariants and raises a `guard.alert`
               event for each new violation. Under a policy that binds approvals (v1), INV-2 is
               stopped at pre_execute and never alerts; under v0 the alert comes after the money
               has gone. The monitor gets its checker from the composition root (vandal.sandbox),
               so Blue never imports the harness or its answer key.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from vandal.twin.state import State


def chain_facts(f: dict[str, Any]) -> dict[str, Any]:
    """The chain summary for a pre_execute verdict, from the facts the gate already has."""
    out: dict[str, Any] = {
        "chain.approved_payee": f.get("approved.payee_account"),
        "chain.executing_payee": f.get("instruction.payee_account"),
        "chain.approved_amount": f.get("approved.amount"),
        "chain.executing_amount": f.get("instruction.amount"),
        "chain.payee_status": f.get("payee_account.status"),
        "chain.payee_verified_by": f.get("payee_account.verified_by"),
    }
    out["chain.binding_ok"] = (
        out["chain.approved_payee"] is not None
        and out["chain.approved_payee"] == out["chain.executing_payee"]
        and out["chain.approved_amount"] == out["chain.executing_amount"]
    )
    out["chain.payee_verified"] = out["chain.payee_status"] == "verified"
    return out


class Finding(Protocol):
    invariant: str
    subject: str
    message: str
    cites: list[str]


Checker = Callable[[State], list[Finding]]


class RuntimeMonitor:
    """Called by the World after each step (twin/world.run_step). Alerts once per
    (invariant, subject)."""

    def __init__(self, checker: Checker) -> None:
        self.checker = checker
        self.seen: set[tuple[str, str]] = set()

    def __call__(self, run, step) -> list[dict[str, Any]]:
        """Raise a guard.alert for each new violation; return them so the World can tell the
        Operator (who opens a case, O2)."""
        alerts = []
        for v in self.checker(run.state):
            key = (v.invariant, v.subject)
            if key in self.seen:
                continue
            self.seen.add(key)
            pay = run.state.payments.get(v.subject)
            payload = {
                "invariant": v.invariant,
                "subject": v.subject,
                "message": v.message,
                "cites": list(v.cites),
                "step": {"index": step.index, "day": step.day, "kind": step.kind},
                "after_execution": pay is not None and pay.status != "scheduled",
            }
            run.emit("guard.alert", payload, actor="blue")
            alerts.append(payload)
        return alerts
