"""R11: money in. Cash application, refunds, T6, INV-11, and Scenario F."""

from __future__ import annotations

from functools import partial

import pytest

from vandal.contracts.moves import Move
from vandal.sandbox import new_sandbox
from vandal.search.alphabet import SCENARIOS
from vandal.search.bfs import search
from vandal.synth.cegis import cegis
from vandal.synth.coverage import diagnose
from vandal.synth.propose import SweepProposer
from vandal.synth.templates import V0, Policy, params_of
from vandal.twin import money_in
from vandal.twin.profile import load_profile
from vandal.verify.invariants import Limits
from vandal.verify.replay import replay, replay_detailed

V2 = Policy.load("policies/v2.json")
V3 = Policy.load("policies/v3.json")
TENANT = "C-004"


def factory_for(policy):
    return partial(new_sandbox, "bayline", policy=policy)


def deposit(at: int = 3, **params) -> Move:
    return Move(kind="deposit", at=at, params={"customer": TENANT, "amount": "overpay", **params})


def refund(dest: str, at: int = 4, party: str = "attacker") -> Move:
    return Move(
        kind="refund_request", at=at, params={"customer": TENANT, "party": party, "dest": dest}
    )


def test_seeded_tenants_owe_rent() -> None:
    state = new_sandbox().run.state
    assert len(state.customers) == 6 and len(state.customer_invoices) == 8
    assert all(c.accounts_on_file for c in state.customers.values())


def test_overpayment_becomes_a_credit_and_comes_back_to_its_source() -> None:
    moves = [deposit(), refund("source", party="customer")]
    result, sb, _ = replay_detailed(7, moves, sandbox=factory_for(V0))
    assert result.violations == []
    state = sb.run.state
    assert all(i.status == "paid" for i in state.customer_invoices.values() if i.customer == TENANT)
    (rf,) = state.refunds.values()
    assert rf.status == "refunded" and rf.amount == 500_000
    assert money_in.credit_balance(state, TENANT) == 0


def test_the_refund_scam_under_v0() -> None:
    moves = [deposit(party="attacker", cleared=0), refund("new")]
    result, sb, _ = replay_detailed(7, moves, sandbox=factory_for(V2))
    assert {"INV-4", "INV-11"} <= set(result.violated) and result.exposure == 500_000
    d = diagnose(sb.run.state, result.violations, Limits.from_profile(sb.profile))
    assert d is not None and d.gap == "refund_destination" and d.payment.startswith("RF-")


def test_refunding_cleared_attacker_money_to_its_source_loses_nothing() -> None:
    moves = [deposit(party="attacker"), refund("source")]
    assert replay(7, moves, sandbox=factory_for(V2)).violations == []


@pytest.mark.parametrize("cleared,dest", [(0, "new"), (0, "source"), (1, "new")])
def test_t6_holds_every_refund_scam(cleared, dest) -> None:
    party = "attacker" if dest != "new" or not cleared else "customer"
    moves = [deposit(party=party, cleared=cleared), refund(dest)]
    result, sb, _ = replay_detailed(7, moves, sandbox=factory_for(V3))
    assert result.violations == []
    assert [r.status for r in sb.run.state.refunds.values()] == ["held"]


def test_a_returned_deposit_reverses_its_application() -> None:
    moves = [deposit(at=0, party="attacker", cleared=0)]
    result, sb, _ = replay_detailed(7, moves, sandbox=factory_for(V0), days=4)
    state = sb.run.state
    assert result.violations == []  # books still tie out after the return
    (payment,) = state.incoming_payments.values()
    assert payment.returned
    assert all(i.status == "open" for i in state.customer_invoices.values() if i.customer == TENANT)


def test_unidentified_deposits_wait_in_suspense() -> None:
    result, sb, _ = replay_detailed(
        7, [deposit(at=0, amount=250_000, memo="none")], sandbox=factory_for(V0)
    )
    (payment,) = sb.run.state.incoming_payments.values()
    assert payment.payer is None and payment.credit == 250_000 and result.violations == []


@pytest.mark.slow
def test_search_finds_the_refund_scam() -> None:
    found = search(factory_for(V2), SCENARIOS["f"], depth=2)
    assert found.best is not None and [m.kind for m in found.best.moves] == [
        "deposit",
        "refund_request",
    ]
    assert search(factory_for(V3), SCENARIOS["f"], depth=2).findings == []


@pytest.mark.slow
def test_cegis_lands_on_t6_with_cleared_funds() -> None:
    profile = load_profile()
    r = cegis(
        V2, factory_for, profile=profile, proposer=SweepProposer(profile), depth=2, scenario="f"
    )
    assert r.status == "repaired" and r.log[0].gap == "refund_destination"
    (added,) = [c for c in r.policy.controls if c not in V2.controls]
    assert added.template == "T6" and params_of(added).require_cleared_funds
    refuted = [e for e in r.log if e.outcome == "counterexample"]
    assert refuted and all("require_cleared_funds=False" in e.candidate for e in refuted)
