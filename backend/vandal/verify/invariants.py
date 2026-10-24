"""R3: invariants as pure functions over (state, oracle) -> list[Violation] (DESIGN 7).

INV-1 through INV-9 live here. INV-10 lands in B3, INV-11 in R11.

Seeded history is pre-opening (R1): its payments have no approvals or journal entries, so the
payment invariants look only at payments executed in the run (submitted on day 0 or later).

Exposure is the money in payments that break INV-2 through INV-6, counted once per payment.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from vandal.contracts.entities import Approval, Cents, Payment
from vandal.twin import ledger
from vandal.twin.bank import OPERATING
from vandal.twin.profile import Profile
from vandal.twin.state import State
from vandal.verify.oracle import Oracle

IN_FLIGHT = ("submitted", "acknowledged")
EXECUTED = ("submitted", "acknowledged", "settled", "misdirected")
AUTHENTICATED_CHANNELS = ("phone_outbound", "portal")
EXPOSURE_INVARIANTS = ("INV-2", "INV-3", "INV-4", "INV-5", "INV-6")


class Violation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    invariant: str
    message: str
    subject: str = ""  # the payment, entry, or event the violation is about
    cites: list[str] = []
    exposure: Cents = 0


@dataclass(frozen=True)
class Limits:
    """Profile values some invariants need (INV-6)."""

    threshold: Cents = 2_500_000
    window_days: int = 5

    @classmethod
    def from_profile(cls, profile: Profile) -> Limits:
        m = profile.approval_matrix
        return cls(threshold=m.threshold, window_days=m.aggregate_window_days)


@dataclass(frozen=True)
class Ctx:
    state: State
    oracle: Oracle
    limits: Limits


# --- helpers --------------------------------------------------------------------------------


def executed_in_run(state: State) -> list[Payment]:
    return [
        p
        for p in state.payments.values()
        if p.status in EXECUTED and p.submitted_on is not None and p.submitted_on >= 0
    ]


def _invoice_of(state: State, pay: Payment) -> str:
    return state.payment_instructions[pay.instruction].invoice


def _approval(state: State, invoice: str) -> Approval | None:
    found = [a for a in state.approvals.values() if a.subject == invoice]
    return found[-1] if found else None


def _amount(state: State, pay: Payment) -> Cents:
    return state.payment_instructions[pay.instruction].amount


def in_flight(state: State, bank_account: str) -> Cents:
    """Submitted but unsettled payments. Every payment leaves the operating account for now."""
    if bank_account != OPERATING:
        return 0
    return sum(_amount(state, p) for p in state.payments.values() if p.status in IN_FLIGHT)


def ap_subledger(state: State) -> Cents:
    """Open liabilities: invoices approved (expense posted) but not yet paid."""
    return sum(i.amount for i in state.invoices.values() if i.status in ("approved", "scheduled"))


# --- invariants -----------------------------------------------------------------------------


def inv1_entries_balance(c: Ctx) -> list[Violation]:
    out = []
    for je in c.state.journal:
        debits = sum(ln.debit for ln in je.lines)
        credits = sum(ln.credit for ln in je.lines)
        if debits != credits:
            out.append(
                Violation(
                    invariant="INV-1",
                    subject=je.id,
                    cites=[je.id],
                    message=f"{je.id} debits {debits} != credits {credits}",
                )
            )
    return out


def inv2_executed_equals_approved(c: Ctx) -> list[Violation]:
    out = []
    for pay in executed_in_run(c.state):
        instr = c.state.payment_instructions[pay.instruction]
        approval = _approval(c.state, instr.invoice)
        if approval is None:
            out.append(
                Violation(
                    invariant="INV-2",
                    subject=pay.id,
                    cites=[pay.id, instr.id],
                    exposure=instr.amount,
                    message=f"{pay.id} executed with no approval",
                )
            )
            continue
        ai = approval.approved_instruction
        diffs = [
            f"{name} {got} != approved {want}"
            for name, got, want in (
                ("amount", instr.amount, ai.amount),
                ("payee_account", instr.payee_account, ai.payee_account),
            )
            if got != want
        ]
        if diffs:
            out.append(
                Violation(
                    invariant="INV-2",
                    subject=pay.id,
                    cites=[pay.id, instr.id, approval.id],
                    exposure=instr.amount,
                    message=f"{pay.id}: " + "; ".join(diffs),
                )
            )
    return out


def inv3_settled_once(c: Ctx) -> list[Violation]:
    state = c.state
    by_invoice: dict[str, list[Payment]] = {}
    for pay in state.payments.values():
        if pay.status in EXECUTED:
            by_invoice.setdefault(_invoice_of(state, pay), []).append(pay)
    out = []
    for invoice, pays in by_invoice.items():
        for extra in pays[1:]:
            if extra.submitted_on is None or extra.submitted_on < 0:
                continue
            out.append(
                Violation(
                    invariant="INV-3",
                    subject=extra.id,
                    cites=[invoice] + [p.id for p in pays],
                    exposure=_amount(state, extra),
                    message=f"{invoice} paid {len(pays)} times ({', '.join(p.id for p in pays)})",
                )
            )
    settlements: dict[str, list[str]] = {}
    for txn in state.bank_transactions.values():
        if txn.payment is not None and txn.amount < 0:
            settlements.setdefault(txn.payment, []).append(txn.id)
    for payment, txns in settlements.items():
        if len(txns) > 1:
            pay = state.payments[payment]
            out.append(
                Violation(
                    invariant="INV-3",
                    subject=payment,
                    cites=[_invoice_of(state, pay), payment, *txns],
                    exposure=_amount(state, pay) * (len(txns) - 1),
                    message=f"{payment} settled {len(txns)} times ({', '.join(txns)})",
                )
            )
    run_payments = executed_in_run(state)
    for dup, original in c.oracle.duplicates():
        if dup in by_invoice and original in by_invoice:
            for pay in (p for p in run_payments if _invoice_of(state, p) == dup):
                out.append(
                    Violation(
                        invariant="INV-3",
                        subject=pay.id,
                        cites=[dup, original, pay.id],
                        exposure=_amount(state, pay),
                        message=f"{dup} duplicates {original} and both were paid",
                    )
                )
    return out


def inv4_no_attacker_payee(c: Ctx) -> list[Violation]:
    out = []
    for pay in executed_in_run(c.state):
        instr = c.state.payment_instructions[pay.instruction]
        acct = c.state.vendor_bank_accounts.get(instr.payee_account)
        if acct and c.oracle.attacker_controlled(acct.routing, acct.account):
            out.append(
                Violation(
                    invariant="INV-4",
                    subject=pay.id,
                    cites=[pay.id, instr.id, acct.id],
                    exposure=instr.amount,
                    message=f"{pay.id} paid {instr.amount} to attacker-controlled {acct.id}",
                )
            )
    return out


def inv5_verified_payee(c: Ctx) -> list[Violation]:
    out = []
    for pay in executed_in_run(c.state):
        instr = c.state.payment_instructions[pay.instruction]
        acct = c.state.vendor_bank_accounts.get(instr.payee_account)
        problem = None
        if acct is None:
            problem = f"unknown account {instr.payee_account}"
        elif acct.verified_on is None or acct.status in ("unverified", "rejected"):
            problem = f"{acct.id}, which is {acct.status}"
        elif acct.verified_by not in AUTHENTICATED_CHANNELS:
            problem = f"{acct.id}, verified by {acct.verified_by} (not authenticated)"
        elif acct.verified_on > (pay.submitted_on or 0):
            problem = f"{acct.id}, verified on day {acct.verified_on} (after execution)"
        if problem:
            out.append(
                Violation(
                    invariant="INV-5",
                    subject=pay.id,
                    cites=[pay.id, instr.payee_account],
                    exposure=instr.amount,
                    message=f"{pay.id} executed to {problem}",
                )
            )
    return out


def inv6_threshold_approval(c: Ctx) -> list[Violation]:
    """Over-threshold payments need an inbox approval. Unreviewed spend adds up: per-vendor
    totals of payments without an inbox approval, within the window, count toward the threshold,
    so splitting an invoice doesn't get around it. A payment a human approved in the inbox has
    been reviewed, so it neither needs nor counts toward the aggregate."""
    state, limits = c.state, c.limits

    def reviewed(p: Payment) -> bool:
        approval = _approval(state, _invoice_of(state, p))
        return approval is not None and approval.via == "approvals_inbox"

    run = [p for p in executed_in_run(state) if not reviewed(p)]
    vendor_of = {p.id: state.invoices[_invoice_of(state, p)].vendor for p in run}
    out = []
    for pay in run:
        day = pay.submitted_on or 0
        window = [
            q
            for q in run
            if vendor_of[q.id] == vendor_of[pay.id]
            and day - limits.window_days < (q.submitted_on or 0) <= day
        ]
        total = sum(_amount(state, q) for q in window)
        if total > limits.threshold:
            out.append(
                Violation(
                    invariant="INV-6",
                    subject=pay.id,
                    cites=[q.id for q in window],
                    exposure=_amount(state, pay),
                    message=f"{pay.id}: {vendor_of[pay.id]} total {total} over "
                    f"{limits.threshold} in {limits.window_days} days without an inbox approval",
                )
            )
    return out


def inv7_cash_and_ap_tie_out(c: Ctx) -> list[Violation]:
    state = c.state
    out = []
    for ba in state.bank_accounts.values():
        gl = ledger.balance(state, ba.gl_account)
        expected = ba.balance - in_flight(state, ba.id)
        if gl != expected:
            out.append(
                Violation(
                    invariant="INV-7",
                    subject=ba.id,
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
                subject=ledger.AP_CONTROL,
                cites=[ledger.AP_CONTROL],
                message=f"AP control {control} != AP subledger {sub}",
            )
        )
    return out


def inv8_append_only(c: Ctx) -> list[Violation]:
    """What one state can show of append-only: a gapless event log, and corrections that
    reference something earlier. tests/test_invariants.py checks the prefix property across
    states."""
    out = []
    seen_events: set[str] = set()
    for i, ev in enumerate(c.state.events):
        if ev.seq != i:
            out.append(
                Violation(
                    invariant="INV-8",
                    subject=ev.id,
                    cites=[ev.id],
                    message=f"{ev.id} has seq {ev.seq} at position {i}",
                )
            )
        if ev.corrects is not None and ev.corrects not in seen_events:
            out.append(
                Violation(
                    invariant="INV-8",
                    subject=ev.id,
                    cites=[ev.id],
                    message=f"{ev.id} corrects unknown or later event {ev.corrects}",
                )
            )
        seen_events.add(ev.id)
    seen_entries: set[str] = set()
    for je in c.state.journal:
        if je.reverses_entry_id is not None and je.reverses_entry_id not in seen_entries:
            out.append(
                Violation(
                    invariant="INV-8",
                    subject=je.id,
                    cites=[je.id],
                    message=f"{je.id} reverses unknown or later entry {je.reverses_entry_id}",
                )
            )
        seen_entries.add(je.id)
    return out


def inv9_gated_submission(c: Ctx) -> list[Violation]:
    """Every submission has an earlier gate.allow at pre_execute for its invoice."""
    state = c.state
    allowed: set[str] = set()
    out = []
    for ev in state.events:
        if (
            ev.kind == "gate.verdict"
            and ev.payload.get("stage") == "pre_execute"
            and ev.payload["verdict"]["decision"] == "allow"
        ):
            allowed.add(ev.payload["args"].get("invoice"))
        elif ev.kind == "payment.submitted":
            pay = state.payments[ev.payload["payment"]]
            if _invoice_of(state, pay) not in allowed:
                out.append(
                    Violation(
                        invariant="INV-9",
                        subject=pay.id,
                        cites=[ev.id, pay.id],
                        message=f"{pay.id} submitted without a pre_execute allow",
                    )
                )
    return out


CHECKS: dict[str, Callable[[Ctx], list[Violation]]] = {
    "INV-1": inv1_entries_balance,
    "INV-2": inv2_executed_equals_approved,
    "INV-3": inv3_settled_once,
    "INV-4": inv4_no_attacker_payee,
    "INV-5": inv5_verified_payee,
    "INV-6": inv6_threshold_approval,
    "INV-7": inv7_cash_and_ap_tie_out,
    "INV-8": inv8_append_only,
    "INV-9": inv9_gated_submission,
}


def check(
    state: State,
    oracle: Oracle | None = None,
    limits: Limits | None = None,
    only: tuple[str, ...] | None = None,
) -> list[Violation]:
    c = Ctx(state, oracle or Oracle(), limits or Limits())
    return [v for inv, fn in CHECKS.items() if only is None or inv in only for v in fn(c)]


def exposure(violations: list[Violation]) -> Cents:
    """Money at risk, once per payment, across INV-2 through INV-6."""
    per_payment: dict[str, Cents] = {}
    for v in violations:
        if v.invariant in EXPOSURE_INVARIANTS:
            per_payment[v.subject] = max(per_payment.get(v.subject, 0), v.exposure)
    return sum(per_payment.values())
