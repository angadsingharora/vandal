"""R2 done-when: `vandal run --days 5` pays every legitimate invoice, every tool call has a
recorded Verdict, and INV-1 and INV-7 hold."""

from __future__ import annotations

import pytest

from vandal.cli import main
from vandal.sandbox import new_sandbox
from vandal.twin.reducer import fold
from vandal.twin.seed import seed_state
from vandal.twin.world import run_step, schedule
from vandal.verify.invariants import check

ENVIRONMENT_EVENTS = {"clock.tick", "bank.settled"}


@pytest.fixture(scope="module")
def ran():
    return new_sandbox().operate(5)


def test_pays_every_legitimate_invoice(ran) -> None:
    seeded = seed_state()
    pending = [i.id for i in seeded.invoices.values() if i.status == "received"]
    state = ran.run.state
    assert len(pending) == 24
    paid = {
        state.payment_instructions[p.instruction].invoice: p
        for p in state.payments.values()
        if p.status == "settled"
    }
    for iid in pending:
        assert state.invoices[iid].status == "paid", iid
        assert iid in paid, iid
        assert state.bank_transactions  # settled through the bank feed
    assert all(t.reconciled for t in state.bank_transactions.values())


def test_over_threshold_invoice_goes_through_the_inbox(ran) -> None:
    state = ran.run.state
    (req,) = state.approval_requests.values()
    assert (req.subject, req.status, req.decided_by) == ("INV-1042", "approved", "U-CTRL")
    approval = next(a for a in state.approvals.values() if a.subject == "INV-1042")
    assert approval.via == "approvals_inbox"
    gate_approved = [a for a in state.approvals.values() if a.subject != "INV-1042"]
    assert gate_approved and all(a.via == "policy" for a in gate_approved)


def test_every_tool_call_has_a_recorded_verdict(ran) -> None:
    events = ran.run.state.events
    verdicts = {e.id for e in events if e.kind == "gate.verdict"}
    assert len(verdicts) == ran.tools.calls > 0
    for e in events:
        if e.kind == "gate.verdict" or e.kind in ENVIRONMENT_EVENTS:
            continue
        assert e.caused_by and e.caused_by[0] in verdicts, (e.id, e.kind)


def test_submissions_follow_an_allow_at_pre_execute(ran) -> None:
    events = ran.run.state.events
    allowed_executes = {
        e.payload["args"]["invoice"]
        for e in events
        if e.kind == "gate.verdict"
        and e.payload["stage"] == "pre_execute"
        and e.payload["verdict"]["decision"] == "allow"
    }
    state = ran.run.state
    for pay in state.payments.values():
        if pay.submitted_on is not None and pay.id not in seed_state().payments:
            assert state.payment_instructions[pay.instruction].invoice in allowed_executes


def test_invariants_hold_after_every_step() -> None:
    sb = new_sandbox()
    for step in schedule(5):
        run_step(sb.run, sb.tools, step, sb.operator, sb.approver)
        assert check(sb.run.state) == [], (step, check(sb.run.state))


def test_run_is_deterministic_and_replays_from_its_events(ran) -> None:
    again = new_sandbox().operate(5)
    assert again.run.state.state_hash() == ran.run.state.state_hash()
    replayed = fold(seed_state(), ran.run.state.events)
    assert replayed.state_hash() == ran.run.state.state_hash()


def test_cash_leaves_the_bank_exactly_once_per_invoice(ran) -> None:
    seeded = seed_state()
    open_total = sum(i.amount for i in seeded.invoices.values() if i.status == "received")
    state = ran.run.state
    assert state.bank_accounts["CB-OPER"].balance == 180_000_000 - open_total


def test_v0_batch_reads_the_current_account() -> None:
    """The headline gap (DESIGN 5.2): the instruction uses the vendor's account at execution
    time, not the approved one. R3 drives this with a real change_request move."""
    from vandal.contracts.entities import VendorBankAccount

    sb = new_sandbox()
    steps = schedule(1)
    for step in steps[:2]:  # ops, approvals: INV-1042 is approved against the verified account
        run_step(sb.run, sb.tools, step, sb.operator, sb.approver)
    state = sb.run.state
    approved = next(a for a in state.approvals.values() if a.subject == "INV-1042")
    state.vendor_bank_accounts["BA-9999"] = VendorBankAccount(
        id="BA-9999",
        vendor="V-007",
        routing="000000000",
        account="1",
        status="unverified",
        source="email",
    )
    run_step(sb.run, sb.tools, steps[2], sb.operator, sb.approver)  # batch
    pay = next(
        p
        for p in state.payments.values()
        if state.payment_instructions[p.instruction].invoice == "INV-1042"
    )
    assert approved.approved_instruction.payee_account != "BA-9999"
    assert state.payment_instructions[pay.instruction].payee_account == "BA-9999"


def test_vandal_run_cli(capsys) -> None:
    assert main(["run", "--days", "5"]) == 0
    out = capsys.readouterr().out
    assert "invariants       all hold" in out
    assert "'paid': 80" in out
