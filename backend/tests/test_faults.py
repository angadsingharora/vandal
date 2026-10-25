"""R10: bank faults, the Operator's retry, T3, and Scenario B."""

from __future__ import annotations

from functools import partial

import pytest

from vandal.contracts.controls import Control
from vandal.contracts.moves import Move
from vandal.sandbox import new_sandbox
from vandal.search.alphabet import SCENARIOS
from vandal.search.bfs import search
from vandal.synth.cegis import cegis
from vandal.synth.propose import SweepProposer
from vandal.synth.templates import V0, Policy
from vandal.twin import ledger
from vandal.twin.profile import load_profile
from vandal.verify.replay import replay, replay_detailed

V1 = Policy.load("policies/v1.json")
V2 = Policy.load("policies/v2.json")
B = SCENARIOS["b"]


def factory_for(policy):
    return partial(new_sandbox, "bayline", policy=policy)


def fault(kind: str, at: int = 2, **params) -> Move:
    return Move(kind="fault", at=at, params={"kind": kind, **params})


def with_t3(on_timeout: str) -> Policy:
    t3 = Control(template="T3", params={"on_timeout": on_timeout})
    return Policy(version="t3", controls=[*V1.controls, t3])


def test_lost_ack_and_a_keyless_retry_pay_twice() -> None:
    result, sb, _ = replay_detailed(7, [fault("drop_ack")], sandbox=factory_for(V1))
    assert result.violated == ["INV-3"] and result.exposure == 4_000_000
    state = sb.run.state
    (pay,) = {s.payment for s in state.bank_submissions.values() if s.idempotency_key is None} & {
        v.subject for v in result.violations
    }
    assert sum(1 for s in state.bank_submissions.values() if s.payment == pay) == 2
    # the books record the second debit as owed back by the vendor, so cash still ties out
    assert ledger.balance(state, ledger.VENDOR_OVERPAYMENT) == 4_000_000


@pytest.mark.parametrize("kind", ["timeout", "duplicate_ack", "delay", "feed_delay"])
def test_other_faults_pay_once(kind) -> None:
    params = {"days": 1} if kind in ("delay", "feed_delay") else {}
    assert replay(7, [fault(kind, **params)], sandbox=factory_for(V1)).violations == []


def test_a_reused_key_is_deduplicated_by_the_bank() -> None:
    _, sb, _ = replay_detailed(
        7, [fault("drop_ack")], sandbox=factory_for(with_t3("retry_with_key"))
    )
    state = sb.run.state
    keyed = [s for s in state.bank_submissions.values() if s.idempotency_key]
    assert keyed and len({s.payment for s in keyed}) == len(keyed)  # one submission per payment
    assert any(e.kind == "bank.ack" and e.payload.get("deduplicated") for e in state.events)


@pytest.mark.parametrize("on_timeout", ["query_status_then_retry", "retry_with_key"])
def test_t3_holds_the_double_payment(on_timeout) -> None:
    for kind in ("drop_ack", "timeout"):
        result = replay(7, [fault(kind)], sandbox=factory_for(with_t3(on_timeout)))
        assert result.violations == [], (kind, result.violated)


def test_search_finds_the_lost_ack() -> None:
    found = search(factory_for(V1), B, depth=1)
    assert found.best is not None and found.best.moves == [fault("drop_ack")]
    assert found.best.violated == ["INV-3"]
    assert search(factory_for(V2), B, depth=1).findings == []


@pytest.mark.slow
def test_cegis_lands_on_t3() -> None:
    profile = load_profile()
    r = cegis(
        V1, factory_for, profile=profile, proposer=SweepProposer(profile), depth=2, scenario="b"
    )
    assert r.status == "repaired" and r.log[0].gap == "execution_idempotency"
    (added,) = [c for c in r.policy.controls if c not in V1.controls]
    assert added.template == "T3" and added.params["on_timeout"] == "query_status_then_retry"


def test_v0_retry_policy_is_keyless_and_query_first_is_safe() -> None:
    from vandal.operator.llm_operator import LLMOperator

    def careful(seed):
        sb = new_sandbox(seed=seed, policy=V0)
        sb.operator = LLMOperator(sb.profile, retry="query_first", use_llm=False)
        return sb

    assert "INV-3" in replay(7, [fault("drop_ack")], sandbox=factory_for(V0)).violated
    assert "INV-3" not in replay(7, [fault("drop_ack")], sandbox=careful).violated
