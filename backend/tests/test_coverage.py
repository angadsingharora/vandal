"""R5 done-when: for R4's counterexample the diagnosis is approval_binding, citing the approval,
the change request, and the payment. Plus every other gap type, and clean chains."""

from __future__ import annotations

from functools import partial

import pytest

from tests.conventions import imported_modules, modules
from tests.test_scenario_a import TRACE
from vandal.cli import main
from vandal.contracts.entities import Approval, ApprovedInstruction, Payment, PaymentInstruction
from vandal.contracts.moves import Move
from vandal.sandbox import new_sandbox
from vandal.search.alphabet import SCENARIOS
from vandal.search.bfs import search
from vandal.synth.coverage import LINKS, EventIndex, build_chain, diagnose
from vandal.verify.invariants import Limits, check
from vandal.verify.replay import replay_detailed

FACTORY = partial(new_sandbox, "bayline")


def kinds_of(state, event_ids):
    return {state.events[int(e.split("-")[1])].kind for e in event_ids}


@pytest.fixture(scope="module")
def counterexample():
    best = search(FACTORY, SCENARIOS["a"], depth=4).best
    result, sb, _ = replay_detailed(7, best.moves, sandbox=FACTORY, days=2)
    return result, sb


@pytest.fixture(scope="module")
def legit():
    return FACTORY(7).operate(2)


def test_r4_counterexample_is_approval_binding(counterexample) -> None:
    result, sb = counterexample
    state = sb.run.state
    d = diagnose(state, result.violations, Limits.from_profile(sb.profile))
    assert d is not None
    assert (d.gap, d.link, d.payment) == ("approval_binding", "execution", "PAY-0057")
    assert d.violated == ["INV-2", "INV-4", "INV-5"] and d.exposure == 4_000_000
    assert d.also == ["verification_channel"]  # DESIGN 11: binding + verification channel

    approval = next(a.id for a in state.approvals.values() if a.subject == "INV-1042")
    (cr,) = state.change_requests
    assert {approval, cr, "PAY-0057"} <= set(d.cites)
    cited_kinds = kinds_of(state, [c for c in d.cites if c.startswith("EV-")])
    assert {"approval.granted", "change_request.created", "instruction.built"} <= cited_kinds
    assert all(c in EventIndex(state.events).by_id for c in d.cites if c.startswith("EV-"))


def test_change_before_approval_is_verification_channel() -> None:
    move = Move(
        kind="change_request",
        at=0,
        params={"vendor": "V-007", "fields": "bank", "channel": "email", "sender": "lookalike"},
    )
    result, sb, _ = replay_detailed(7, [move], sandbox=FACTORY, days=2)
    d = diagnose(sb.run.state, result.violations)
    assert (d.gap, d.link) == ("verification_channel", "execution")
    assert d.also == []  # the approval bound the attacker's account, so binding held
    assert "CR-0001" in d.cites and "MSG-0001" in d.cites


def test_legitimate_chains_are_fully_covered(legit) -> None:
    state = legit.run.state
    in_run = [
        p.id for p in state.payments.values() if p.submitted_on is not None and p.submitted_on >= 0
    ]
    assert len(in_run) == 24
    index = EventIndex(state.events)
    for pay in in_run:
        chain = build_chain(state, pay, index=index)
        assert [ln.name for ln in chain.links] == list(LINKS)
        assert all(ln.status == "covered" for ln in chain.links), chain
        assert chain.first_uncovered is None
        # Every link points at real records, so B5 can cite them.
        assert all(ln.events for ln in chain.links), chain
    assert diagnose(state, check(state)) is None


def test_history_payment_chain() -> None:
    state = FACTORY(7).run.state
    chain = build_chain(state, "PAY-0001")
    assert chain.links[-1].reason == "pre-opening history"


def _approve(state, aid, invoice, amount, payee, via="policy"):
    inv = state.invoices[invoice]
    ai = ApprovedInstruction(
        invoice=invoice, amount=amount, payee_account=payee, due_date=inv.due_date
    )
    state.put(
        "approvals",
        Approval(
            id=aid,
            subject=invoice,
            requested_by="OP-1",
            approver="gate",
            via=via,
            approved_instruction=ai,
            instruction_hash="x",
        ),
    )


def _pay(state, pid, invoice, amount, payee, day=0):
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


def _policy_payment(state):
    policy = {a.subject for a in state.approvals.values() if a.via == "policy"}
    pay = next(
        p
        for p in state.payments.values()
        if p.submitted_on == 0 and state.payment_instructions[p.instruction].invoice in policy
    )
    return pay, state.payment_instructions[pay.instruction]


def test_retry_double_pay_is_execution_idempotency(legit) -> None:
    state = legit.run.state.clone()
    pay, instr = _policy_payment(state)
    _pay(state, "RETRY", instr.invoice, instr.amount, instr.payee_account, day=1)
    d = diagnose(state, check(state))
    assert (d.gap, d.link) == ("execution_idempotency", "execution")
    assert {pay.id, "PAY-RETRY"} <= set(d.cites)


def test_suffix_duplicate_is_duplicate_obligation(legit) -> None:
    state = legit.run.state.clone()
    pay, instr = _policy_payment(state)
    inv = state.invoices[instr.invoice]
    state.put("invoices", inv.model_copy(update={"id": "INV-DUPA", "number": inv.number + "A"}))
    _approve(state, "APR-DUPA", "INV-DUPA", inv.amount, instr.payee_account)
    _pay(state, "DUPA", "INV-DUPA", inv.amount, instr.payee_account)
    chain = build_chain(state, "PAY-DUPA")
    first = chain.first_uncovered
    assert (first.name, first.gap) == ("obligation", "duplicate_obligation")
    assert inv.id in first.entities


def test_split_invoices_are_aggregate_threshold(legit) -> None:
    state = legit.run.state.clone()
    pay, instr = _policy_payment(state)
    inv = state.invoices[instr.invoice]
    other = 2_500_000 - instr.amount + 1
    state.put(
        "invoices", inv.model_copy(update={"id": "INV-SPLIT", "number": "SPLIT-2", "amount": other})
    )
    _approve(state, "APR-SPLIT", "INV-SPLIT", other, instr.payee_account)
    _pay(state, "SPLIT", "INV-SPLIT", other, instr.payee_account)
    d = diagnose(state, check(state))
    assert (d.gap, d.link) == ("aggregate_threshold", "approval")
    assert "INV-6" in d.violated


def test_coverage_never_reads_the_oracle() -> None:
    paths = modules("synth")
    names = [n for p in paths for _, n in imported_modules(p)]
    assert not [n for n in names if n.startswith("vandal.verify.oracle")]


def test_attack_cli_prints_the_diagnosis(capsys) -> None:
    assert main(["attack", "--trace", str(TRACE)]) == 0
    out = capsys.readouterr().out
    assert "diagnosis: approval_binding at the execution link of PAY-0057" in out
    assert "(also: verification_channel)" in out
