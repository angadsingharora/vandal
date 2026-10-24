"""Invariants as pure functions check(state) -> list[Violation] (DESIGN 7).

R2 ships INV-1 and INV-7, which its done-when needs. R3 adds INV-2 through INV-6 and INV-9.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from vandal.contracts.entities import Cents
from vandal.twin import ledger
from vandal.twin.bank import OPERATING
from vandal.twin.state import State

IN_FLIGHT = ("submitted", "acknowledged")


class Violation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    invariant: str
    message: str
    cites: list[str] = []
    exposure: Cents = 0


def inv1_entries_balance(state: State) -> list[Violation]:
    out = []
    for je in state.journal:
        debits = sum(ln.debit for ln in je.lines)
        credits = sum(ln.credit for ln in je.lines)
        if debits != credits:
            out.append(
                Violation(
                    invariant="INV-1",
                    cites=[je.id],
                    message=f"{je.id} debits {debits} != credits {credits}",
                )
            )
    return out


def in_flight(state: State, bank_account: str) -> Cents:
    """Submitted but unsettled payments. Every payment leaves the operating account for now."""
    if bank_account != OPERATING:
        return 0
    return sum(
        state.payment_instructions[p.instruction].amount
        for p in state.payments.values()
        if p.status in IN_FLIGHT
    )


def ap_subledger(state: State) -> Cents:
    """Open liabilities: invoices approved (expense posted) but not yet paid."""
    return sum(i.amount for i in state.invoices.values() if i.status in ("approved", "scheduled"))


def inv7_cash_and_ap_tie_out(state: State) -> list[Violation]:
    out = []
    for ba in state.bank_accounts.values():
        gl = ledger.balance(state, ba.gl_account)
        expected = ba.balance - in_flight(state, ba.id)
        if gl != expected:
            out.append(
                Violation(
                    invariant="INV-7",
                    cites=[ba.id, ba.gl_account],
                    message=f"GL {ba.gl_account} = {gl}, bank {ba.id} - in-flight = {expected}",
                )
            )
    control = -ledger.balance(state, ledger.AP_CONTROL)
    sub = ap_subledger(state)
    if control != sub:
        out.append(
            Violation(
                invariant="INV-7",
                cites=[ledger.AP_CONTROL],
                message=f"AP control {control} != AP subledger {sub}",
            )
        )
    return out


CHECKS: dict[str, Callable[[State], list[Violation]]] = {
    "INV-1": inv1_entries_balance,
    "INV-7": inv7_cash_and_ap_tie_out,
}


def check(state: State) -> list[Violation]:
    return [v for fn in CHECKS.values() for v in fn(state)]
