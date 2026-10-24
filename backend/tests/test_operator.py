"""O2 and O3 done-whens. O2: after Scenario A under v0, the books show the receivable and the
reinstated AP, and INV-1 and INV-7 hold. O3: a denied invoice goes to held with its reason
recorded, slow approvers are reminded and escalated, and refunds flow through Blue (the money-in
tests cover that path). O1 (LLM intake) isn't built."""

from __future__ import annotations

from functools import partial
from pathlib import Path

from vandal.contracts.entities import Actor
from vandal.contracts.moves import Move
from vandal.sandbox import new_sandbox
from vandal.twin import ledger
from vandal.twin.flows import InvoiceRef, ScheduleArgs
from vandal.twin.profile import load_profile
from vandal.twin.world import run_step, schedule
from vandal.verify.invariants import check
from vandal.verify.oracle import Oracle
from vandal.verify.replay import HarnessEnvironment, Trace, apply_move, replay_detailed

TRACE = Path(__file__).resolve().parents[1] / "scenarios" / "a_manual.json"
OP = Actor(id="OP-1", role="operator")


def run(sb, moves, days, each_step=None):
    """Drive the World step by step, applying moves like replay does."""
    oracle = Oracle()
    for step in schedule(days):
        for i, m in enumerate(moves):
            if m.at == step.index:
                apply_move(sb, m, i, oracle)
        run_step(sb.run, sb.tools, step, sb.operator, sb.approver, HarnessEnvironment(oracle))
        if each_step:
            each_step(step, sb.run.state)
    return sb.run.state


# --- O2 -------------------------------------------------------------------------------------


def test_o2_books_show_the_receivable_and_reinstated_ap() -> None:
    sb = new_sandbox(monitor=True)
    seen = {}

    def books(step, state):
        broken = [v.invariant for v in check(state) if v.invariant in ("INV-1", "INV-7")]
        assert broken == [], (step, broken)
        if step.day == 0 and step.kind == "batch":
            seen["receivable"] = ledger.balance(state, ledger.MISDIRECTED_RECEIVABLE)
            seen["ap"] = -ledger.balance(state, ledger.AP_CONTROL)
            seen["invoice"] = state.invoices["INV-1042"].status

    state = run(sb, Trace.load(TRACE).moves, days=4, each_step=books)
    assert seen["receivable"] == 4_000_000
    assert seen["ap"] >= 4_000_000 and seen["invoice"] == "approved"  # liability reinstated
    assert ledger.balance(state, ledger.MISDIRECTED_RECEIVABLE) == 4_000_000  # recall failed


def test_o2_recovery_runs_through_blue_and_the_inbox() -> None:
    sb = new_sandbox(monitor=True)
    state = run(sb, Trace.load(TRACE).moves, days=4)
    (case,) = state.cases.values()
    assert case.kind == "recovery" and case.subject == "PAY-0057"
    assert case.actions[:4] == [
        "marked PAY-0057 misdirected",
        "asked the bank to recall PAY-0057",
        "rejected BA-0032, restored BA-0007",
        "asked to re-pay INV-1042",
    ]
    assert case.status == "resolved" and "receivable to pursue" in case.outcome
    assert state.payments["PAY-0057"].recall == "failed"
    assert state.vendor_bank_accounts["BA-0032"].status == "rejected"
    assert state.vendor_bank_accounts["BA-0007"].status == "verified"
    repayment = next(r for r in state.approval_requests.values() if r.kind == "repayment")
    assert repayment.decided_by == "U-CTRL" and repayment.instruction.payee_account == "BA-0007"
    repaid = [
        p
        for p in state.payments.values()
        if p.id != "PAY-0057" and state.payment_instructions[p.instruction].invoice == "INV-1042"
    ]
    assert len(repaid) == 1 and repaid[0].status == "settled"
    assert state.payment_instructions[repaid[0].instruction].payee_account == "BA-0007"
    verdicts = [
        e.payload
        for e in state.events
        if e.kind == "gate.verdict" and e.payload["tool"] == "approvals.request_repayment"
    ]
    assert verdicts[0]["verdict"]["decision"] == "escalate"  # a human, at any amount
    assert "blue.repayment_inbox" in verdicts[0]["verdict"]["fired"]
    assert "INV-3" not in {v.invariant for v in check(state)}  # re-paying isn't double paying


def test_o2_repayment_waits_for_its_approval() -> None:
    sb = new_sandbox(monitor=True)
    run(sb, Trace.load(TRACE).moves, days=1)  # misdirected, re-payment requested, not decided
    tools = sb.tools
    if tools.view.invoices["INV-1042"].status == "approved":
        tools.call(OP, "payments.schedule", ScheduleArgs(invoice="INV-1042", pay_on=1))
    result = tools.call(OP, "payments.execute", InvoiceRef(invoice="INV-1042"))
    assert result.verdict.decision == "hold"
    assert "blue.repayment_before_execute" in result.verdict.fired


def test_o2_a_vendor_inquiry_opens_the_case_without_the_monitor() -> None:
    inquiry = Move(
        kind="message",
        at=5,
        params={"vendor": "V-007", "party": "vendor", "channel": "email", "asks": "payment_status"},
    )
    sb = new_sandbox()  # Blue's monitor off: the vendor's call is what surfaces it
    state = run(sb, [*Trace.load(TRACE).moves, inquiry], days=2)
    (case,) = state.cases.values()
    assert case.subject == "PAY-0057" and "reports non-payment" in case.reason
    assert state.payments["PAY-0057"].status == "misdirected"


def test_o2_legitimate_runs_open_no_cases() -> None:
    state = new_sandbox(monitor=True).operate(5).run.state
    assert state.cases == {} and check(state) == []


# --- O3 -------------------------------------------------------------------------------------


def _slow_controller():
    profile = load_profile()
    approvers = [
        a.model_copy(update={"response_days": 9 if a.id == "U-CTRL" else 0})
        for a in profile.approval_matrix.approvers
    ]
    matrix = profile.approval_matrix.model_copy(update={"approvers": approvers})
    return profile.model_copy(update={"approval_matrix": matrix})


def test_o3_slow_approvers_are_reminded_then_escalated() -> None:
    sb = new_sandbox(_slow_controller())
    state = sb.operate(6).run.state
    (req,) = state.approval_requests.values()
    assert req.reminders == 1 and req.assigned_to == "U-CFO"
    assert (req.status, req.decided_by) == ("approved", "U-CFO")
    kinds = [e.kind for e in state.events]
    assert kinds.index("approval.reminded") < kinds.index("approval.reassigned")
    reminded = next(e for e in state.events if e.kind == "approval.reminded")
    reassigned = next(e for e in state.events if e.kind == "approval.reassigned")
    assert (reminded.day, reassigned.day) == (2, 4)
    assert state.invoices["INV-1042"].status == "paid"


def test_o3_a_denied_invoice_is_held_with_its_reason() -> None:
    bill = Move(
        kind="submit_invoice",
        at=0,
        params={"vendor": "V-023", "number": "RR23-77", "amount": 3_000_000, "party": "vendor"},
    )
    sb = new_sandbox()
    state = run(sb, [bill], days=3)
    inv = next(i for i in state.invoices.values() if i.number == "RR23-77")
    reqs = [r for r in state.approval_requests.values() if r.subject == inv.id]
    assert inv.status == "held"
    assert len(reqs) == 1 and reqs[0].status == "denied"  # never resubmitted unchanged
    assert "prior payments" in reqs[0].reason
    assert not any(
        state.payment_instructions[p.instruction].invoice == inv.id for p in state.payments.values()
    )


def test_o3_refunds_and_cash_application_go_through_the_gate() -> None:
    """A customer overpays; the credit is refunded to its source. Every cash application and
    the refund are gate calls with recorded verdicts."""
    from tests.test_money_in import deposit, refund

    result, sb, _ = replay_detailed(
        7, [deposit(), refund("source", party="customer")], sandbox=partial(new_sandbox, "bayline")
    )
    state = sb.run.state
    assert result.violations == []
    (refund,) = state.refunds.values()
    tools = {e.payload["tool"] for e in state.events if e.kind == "gate.verdict"}
    assert {"cash.apply", "refunds.issue"} <= tools
    money_events = [e for e in state.events if e.kind.startswith(("cash.", "refund."))]
    assert money_events and all(
        e.caused_by and state.events[int(e.caused_by[0].split("-")[1])].kind == "gate.verdict"
        for e in money_events
    )
