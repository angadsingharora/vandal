"""Each invariant catches its own violation and stays quiet on legitimate operations."""

from __future__ import annotations

import pytest

from vandal.contracts.entities import (
    Approval,
    ApprovedInstruction,
    JournalEntry,
    JournalLine,
    Payment,
    PaymentInstruction,
)
from vandal.sandbox import new_sandbox
from vandal.twin.world import run_step, schedule
from vandal.verify.invariants import CHECKS, Limits, check, exposure
from vandal.verify.oracle import Oracle


@pytest.fixture(scope="module")
def legit():
    return new_sandbox().operate(2)


@pytest.fixture
def state(legit):
    return legit.run.state.clone()


def run_payment(state):
    """A payment made in the run for an invoice the gate approved by policy."""
    policy = {a.subject for a in state.approvals.values() if a.via == "policy"}
    return next(
        p
        for p in state.payments.values()
        if p.submitted_on == 0 and state.payment_instructions[p.instruction].invoice in policy
    )


def add_payment(state, pid: str, invoice: str, amount: int, payee: str, day: int = 0) -> None:
    state.put(
        "payment_instructions",
        PaymentInstruction(id=f"PI-{pid}", invoice=invoice, amount=amount, payee_account=payee),
    )
    state.put(
        "payments",
        Payment(
            id=f"PAY-{pid}",
            instruction=f"PI-{pid}",
            status="settled",
            attempts=1,
            submitted_on=day,
            settled_on=day + 1,
        ),
    )


def test_all_invariants_hold_on_legitimate_ops(legit) -> None:
    assert set(CHECKS) == {f"INV-{n}" for n in range(1, 10)}
    assert check(legit.run.state) == []


def test_inv1_unbalanced_entry(state) -> None:
    state.journal.append(
        JournalEntry(
            id="JE-X",
            posted_on=1,
            lines=[JournalLine(account="5100", debit=100), JournalLine(account="2000", credit=99)],
        )
    )
    (v,) = check(state, only=("INV-1",))
    assert v.subject == "JE-X"


def test_inv2_amount_mismatch(state) -> None:
    pay = run_payment(state)
    instr = state.payment_instructions[pay.instruction]
    state.update("payment_instructions", instr.id, amount=instr.amount + 1)
    (v,) = check(state, only=("INV-2",))
    assert v.subject == pay.id and "amount" in v.message


def test_inv3_paid_twice_and_oracle_duplicate(state) -> None:
    pay = run_payment(state)
    instr = state.payment_instructions[pay.instruction]
    add_payment(state, "DUP", instr.invoice, instr.amount, instr.payee_account, day=1)
    (v,) = check(state, only=("INV-3",))
    assert v.subject == "PAY-DUP" and v.exposure == instr.amount

    clean = state.clone()
    del clean.payments["PAY-DUP"]
    inv = clean.invoices[instr.invoice]
    clean.put("invoices", inv.model_copy(update={"id": "INV-NEAR", "number": inv.number + "A"}))
    add_payment(clean, "NEAR", "INV-NEAR", instr.amount, instr.payee_account)
    oracle = Oracle()
    oracle.add("INV-NEAR", "duplicate_of", instr.invoice)
    assert check(clean, only=("INV-3",)) == []  # without the answer key it looks legitimate
    (v,) = check(clean, oracle, only=("INV-3",))
    assert v.subject == "PAY-NEAR"


def test_inv4_needs_the_oracle(state) -> None:
    pay = run_payment(state)
    acct = state.vendor_bank_accounts[state.payment_instructions[pay.instruction].payee_account]
    oracle = Oracle()
    oracle.add(f"acct:{acct.routing}:{acct.account}", "attacker_controlled")
    assert check(state, only=("INV-4",)) == []
    (v,) = check(state, oracle, only=("INV-4",))
    assert v.subject == pay.id


@pytest.mark.parametrize(
    ("changes", "needle"),
    [
        ({"status": "unverified"}, "unverified"),
        ({"verified_by": "email"}, "not authenticated"),
        ({"verified_on": 3}, "after execution"),
    ],
)
def test_inv5_payee_not_verified_in_time(state, changes, needle) -> None:
    pay = run_payment(state)
    state.update(
        "vendor_bank_accounts", state.payment_instructions[pay.instruction].payee_account, **changes
    )
    (v,) = check(state, only=("INV-5",))
    assert needle in v.message


def test_inv6_split_under_threshold(state) -> None:
    pay = run_payment(state)
    instr = state.payment_instructions[pay.instruction]
    inv = state.invoices[instr.invoice]
    other = 2_500_000 - instr.amount + 1  # together they cross $25k
    state.put(
        "invoices", inv.model_copy(update={"id": "INV-SPLIT", "number": "SPLIT", "amount": other})
    )
    ai = ApprovedInstruction(
        invoice="INV-SPLIT", amount=other, payee_account=instr.payee_account, due_date=inv.due_date
    )
    state.put(
        "approvals",
        Approval(
            id="APR-SPLIT",
            subject="INV-SPLIT",
            requested_by="OP-1",
            approver="gate",
            via="policy",
            approved_instruction=ai,
            instruction_hash="x",
        ),
    )
    add_payment(state, "SPLIT", "INV-SPLIT", other, instr.payee_account)
    violations = check(state, only=("INV-6",))
    assert {v.subject for v in violations} == {pay.id, "PAY-SPLIT"}
    assert check(state, limits=Limits(threshold=10_000_000), only=("INV-6",)) == []


def test_inv7_bank_and_books_disagree(state) -> None:
    bank = state.bank_accounts["CB-OPER"]
    state.update("bank_accounts", "CB-OPER", balance=bank.balance - 1)
    (v,) = check(state, only=("INV-7",))
    assert v.subject == "CB-OPER"


def test_inv8_logs_only_grow() -> None:
    sb = new_sandbox()
    snapshots = []
    for step in schedule(2):
        run_step(sb.run, sb.tools, step, sb.operator, sb.approver)
        snapshots.append((list(sb.run.state.events), list(sb.run.state.journal)))
    final_events, final_journal = sb.run.state.events, sb.run.state.journal
    for events, journal in snapshots:
        assert final_events[: len(events)] == events
        assert final_journal[: len(journal)] == journal


def test_inv8_reversal_must_reference_an_earlier_entry(state) -> None:
    state.journal.append(
        JournalEntry(id="JE-R", posted_on=1, lines=[], reverses_entry_id="JE-9999")
    )
    (v,) = check(state, only=("INV-8",))
    assert v.subject == "JE-R"


def test_inv9_ungated_submission() -> None:
    """A bug that bypasses Tools (emitting events directly) shows up as INV-9."""
    sb = new_sandbox()
    sb.run.emit(
        "instruction.built",
        {
            "instruction": {
                "id": "PI-X",
                "invoice": "INV-1042",
                "amount": 4_000_000,
                "payee_account": "BA-0007",
            },
            "payment": {"id": "PAY-X", "instruction": "PI-X"},
        },
    )
    sb.run.emit("payment.submitted", {"payment": "PAY-X"})
    (v,) = check(sb.run.state, only=("INV-9",))
    assert v.subject == "PAY-X"


def test_exposure_counts_each_payment_once(state) -> None:
    pay = run_payment(state)
    instr = state.payment_instructions[pay.instruction]
    state.update("payment_instructions", instr.id, amount=instr.amount + 1)
    state.update("vendor_bank_accounts", instr.payee_account, status="unverified")
    violations = check(state)
    assert {v.invariant for v in violations} >= {"INV-2", "INV-5"}
    assert exposure(violations) == instr.amount + 1
