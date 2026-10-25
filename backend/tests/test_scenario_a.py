"""R3 done-when: Scenario A by hand gives INV-2 and INV-4 with exposure 4,000,000 cents, the
books still balance, the same trace gives the same hash, and `vandal attack` prints it."""

from __future__ import annotations

from pathlib import Path

import pytest

from vandal.cli import main
from vandal.contracts.moves import Move
from vandal.sandbox import new_sandbox, replay_deterministic
from vandal.verify.replay import IllegalMove, Trace, lookalike, replay, replay_detailed

TRACE = Path(__file__).resolve().parents[1] / "scenarios" / "a_manual.json"


@pytest.fixture(scope="module")
def trace() -> Trace:
    return Trace.load(TRACE)


@pytest.fixture(scope="module")
def result(trace):
    return replay_deterministic(trace)


def test_scenario_a_violates_inv2_and_inv4(result) -> None:
    assert {"INV-2", "INV-4"} <= set(result.violated)
    assert result.exposure == 4_000_000


def test_scenario_a_matches_design_and_books_balance(result) -> None:
    # DESIGN 11: Scenario A violates INV-2, INV-4, INV-5. The books stay correct (INV-1, INV-7):
    # the money left through properly posted entries; it just went to the wrong place.
    assert result.violated == ["INV-2", "INV-4", "INV-5"]
    assert {v.subject for v in result.violations} == {"PAY-0057"}


def test_same_trace_same_hash(trace, result) -> None:
    again = replay_deterministic(trace)
    assert again.state_hash == result.state_hash
    assert again.violations == result.violations


def test_attack_shape(trace) -> None:
    _, sb, oracle = replay_detailed(
        trace.seed, trace.moves, sandbox=lambda s: new_sandbox(seed=s), days=trace.days
    )
    state = sb.run.state
    (cr,) = state.change_requests.values()
    assert (cr.vendor, cr.channel, cr.status) == ("V-007", "email", "applied")
    assert cr.sender.endswith("@harborpointbui1d.com")
    approval = next(a for a in state.approvals.values() if a.subject == "INV-1042")
    pay = state.payments["PAY-0057"]
    instr = state.payment_instructions[pay.instruction]
    assert instr.invoice == "INV-1042" and pay.status == "settled"
    assert approval.approved_instruction.payee_account == "BA-0007"
    assert instr.payee_account == cr_account(state, cr.id)
    # Every other invoice still went to its verified account.
    others = [p for p in state.payments.values() if p.id != "PAY-0057" and p.submitted_on >= 0]
    assert others and all(
        state.vendor_bank_accounts[state.payment_instructions[p.instruction].payee_account].status
        == "verified"
        for p in others
    )


def cr_account(state, cr_id: str) -> str:
    return next(
        a.id for a in state.vendor_bank_accounts.values() if a.source == f"change_request:{cr_id}"
    )


def test_no_moves_no_violations() -> None:
    r = replay(7, [], sandbox=lambda s: new_sandbox(seed=s))
    assert r.violations == [] and r.exposure == 0


def test_change_before_approval_is_a_different_violation() -> None:
    """With the change landing before approval, the approval binds the attacker's account: INV-2
    holds but INV-4 and INV-5 don't. This is why T2 alone isn't enough (DESIGN 11)."""
    moves = [
        Move(
            kind="change_request",
            at=0,
            params={"vendor": "V-007", "fields": "bank", "channel": "email", "sender": "lookalike"},
        )
    ]
    r = replay(7, moves, sandbox=lambda s: new_sandbox(seed=s))
    assert r.violated == ["INV-4", "INV-5"]
    assert r.exposure == 4_000_000


def test_illegal_and_unbuilt_moves_are_rejected() -> None:
    portal = Move(
        kind="change_request",
        at=0,
        params={"vendor": "V-007", "channel": "portal", "sender": "lookalike"},
    )
    with pytest.raises(IllegalMove):
        replay(7, [portal], sandbox=lambda s: new_sandbox(seed=s))
    with pytest.raises(IllegalMove, match="bank fault"):
        replay(7, [Move(kind="fault", at=0, params={})], sandbox=lambda s: new_sandbox(seed=s))


def test_lookalike_domains() -> None:
    assert lookalike("harborpointbuild.com") == "harborpointbui1d.com"
    assert lookalike("rentroll.io") == "rentrol1.io"
    assert lookalike("abc.com") == "abc-billing.com"


def test_vandal_attack_prints_the_violation(capsys) -> None:
    assert main(["attack", "--trace", str(TRACE)]) == 0
    out = capsys.readouterr().out
    assert "VIOLATED INV-2, INV-4, INV-5" in out
    assert "(4000000 cents)" in out


def test_gate_had_every_fact_it_needed(trace) -> None:
    """The fail-closed path (gate.missing_facts) would mean facts.py has a gap."""
    for days, moves in ((5, []), (trace.days, trace.moves)):
        _, sb, _ = replay_detailed(7, moves, sandbox=lambda s: new_sandbox(seed=s), days=days)
        verdicts = [e for e in sb.run.state.events if e.kind == "gate.verdict"]
        assert verdicts
        assert not [e.id for e in verdicts if "gate.missing_facts" in e.payload["verdict"]["facts"]]
