"""R9 (partial): composed traces with their own answer key, impersonation messages, search
seeded with injected moves, and CEGIS starting from a given counterexample. Plain-language
inject and Red-written content aren't built yet."""

from __future__ import annotations

from functools import partial

import pytest

from vandal.contracts.controls import Control
from vandal.contracts.entities import OracleLabel
from vandal.contracts.moves import Move
from vandal.sandbox import new_sandbox
from vandal.search.alphabet import SCENARIOS
from vandal.search.bfs import search
from vandal.search.minimize import minimize_trace
from vandal.synth.cegis import cegis
from vandal.synth.propose import Proposal, SweepProposer
from vandal.synth.templates import V0, Policy
from vandal.twin.profile import load_profile
from vandal.verify.oracle import account_key
from vandal.verify.replay import IllegalMove, Trace, replay, replay_detailed, replay_trace

V1 = Policy.load("policies/v1.json")
A = SCENARIOS["a"]


def factory_for(policy):
    return partial(new_sandbox, "bayline", policy=policy)


def change(at: int, vendor: str = "V-007") -> Move:
    return Move(
        kind="change_request",
        at=at,
        params={"vendor": vendor, "fields": "bank", "channel": "email", "sender": "lookalike"},
    )


def exec_call(channel: str = "phone_in") -> Move:
    return Move(
        kind="message",
        at=0,
        params={
            "poses_as": "CFO",
            "party": "attacker",
            "channel": channel,
            "text": "placeholder content",
        },
    )


def test_composed_labels_seed_the_oracle() -> None:
    """A composed trace can assert facts the moves alone don't: here, that a seeded account
    already belongs to the attacker."""
    sb = new_sandbox()
    account = sb.run.state.vendor_bank_accounts["BA-0007"]
    label = OracleLabel(
        subject=account_key(account.routing, account.account), label="attacker_controlled"
    )
    trace = Trace(name="composed", moves=[], labels=[label])
    result = replay_trace(trace, sandbox=factory_for(None))
    assert "INV-4" in result.violated
    assert replay(7, [], sandbox=factory_for(None)).violations == []


def test_executive_impersonation_is_labeled_and_moves_no_money() -> None:
    result, sb, oracle = replay_detailed(7, [exec_call()], sandbox=factory_for(None))
    state = sb.run.state
    (event,) = [e for e in state.events if e.kind == "channel.received"]
    msg = event.payload["message"]
    assert (msg["channel"], msg["sender"], msg["meta"]["poses_as"]) == ("phone_in", "U-CFO", "CFO")
    assert oracle.has(msg["id"], "true_sender") and oracle.has(msg["id"], "deepfake")
    assert result.violations == []  # no tool pays outside an approved invoice


def test_impersonation_respects_attacker_capabilities() -> None:
    profile = load_profile()
    honest = profile.model_copy(
        update={
            "attacker_capabilities": profile.attacker_capabilities.model_copy(
                update={"spoof_caller_id": False, "clone_voice": False}
            )
        }
    )
    with pytest.raises(IllegalMove):
        replay(7, [exec_call("phone_in")], sandbox=partial(new_sandbox, honest))


def test_seeded_search_depth_zero_is_the_injected_moves() -> None:
    r = search(factory_for(None), A, depth=2, around=[change(2)])
    assert r.levels == [] and r.best is not None
    assert r.best.moves == [change(2)] and {"INV-2", "INV-4"} <= set(r.best.violated)


def test_seeded_search_includes_the_seed_and_minimizing_drops_it_if_unneeded() -> None:
    r = search(factory_for(None), A, depth=1, around=[exec_call()])
    best = r.best
    assert best is not None and exec_call() in best.moves  # every sequence carries the seed

    def violated(moves):
        return set(replay(7, moves, sandbox=factory_for(None)).violated)

    minimal = minimize_trace(best.moves, violated)
    assert exec_call() not in minimal  # the call wasn't what broke it


def test_seeded_search_holds_under_v1() -> None:
    r = search(factory_for(V1), A, depth=1, around=[exec_call()])
    assert r.findings == [] and r.levels == [r.alphabet]


@pytest.mark.slow
def test_cegis_starts_from_a_given_counterexample() -> None:
    profile = load_profile()
    t2 = Policy(
        version="t2", controls=[Control(template="T2", params={"bound_fields": ["payee_account"]})]
    )
    r = cegis(
        t2,
        factory_for,
        profile=profile,
        proposer=SweepProposer(profile),
        depth=2,
        workers=4,
        start=[change(0)],
    )
    assert r.status == "repaired"
    assert r.log[0].gap == "verification_channel"  # diagnosed from the given trace, not search


def test_cegis_with_a_harmless_start_has_nothing_to_repair() -> None:
    profile = load_profile()
    r = cegis(
        V0,
        factory_for,
        profile=profile,
        proposer=SweepProposer(profile),
        depth=1,
        start=[exec_call()],
    )
    assert r.status == "nothing_to_repair" and "breaks nothing" in r.reason


@pytest.mark.slow
def test_candidates_must_hold_against_the_given_counterexample() -> None:
    """Search alone may never reach an injected threat, so a candidate that leaves it working
    is refuted by replaying it, not reported as a survivor."""

    class OnlyT3:
        name = "test"

        def propose(self, ctx):
            t3 = Control(template="T3", params={})  # idempotency: does nothing for a redirect
            return [Proposal(controls=[t3], rationale="", source="sweep")]

    profile = load_profile()
    r = cegis(
        V0,
        factory_for,
        profile=profile,
        proposer=OnlyT3(),
        depth=0,
        max_iterations=1,
        start=[change(2)],
    )
    assert r.status == "cannot_auto_repair"
    (entry,) = r.log
    assert entry.outcome == "counterexample" and entry.counterexample == [change(2)]


# --- R9: Red, plain-language inject, `vandal inject` ------------------------------------------

from vandal import llm  # noqa: E402
from vandal.cli import main  # noqa: E402
from vandal.search import red  # noqa: E402

CFO = "the CFO calls from an airport asking for an urgent wire to a new supplier"


@pytest.mark.parametrize(
    "description,scenario,kinds",
    [
        (CFO, "a", ["message"]),
        (
            "a vendor emails new bank details after approval, then calls to confirm",
            "a",
            ["change_request", "inbound_confirmation"],
        ),
        (
            "a tenant overpays and asks for a refund to a new account",
            "f",
            ["deposit", "refund_request"],
        ),
        ("the bank loses the ack during the payment run", "b", ["fault"]),
    ],
)
def test_keyword_reader_maps_the_modeled_threats(description, scenario, kinds) -> None:
    p = red.plan(description, factory_for(None), use_llm=False)
    assert p.scenario == scenario and [m.kind for m in p.moves] == kinds
    assert all("text" in m.params for m in p.moves if red.template_for(m))


def test_the_cfo_call_says_what_isnt_modeled() -> None:
    p = red.plan(CFO, factory_for(None), use_llm=False)
    (move,) = p.moves
    assert move.params["poses_as"] == "CFO" and move.params["channel"] == "phone_in"
    assert "It's the CFO" in move.params["text"]
    assert any("not modeled" in n for n in p.notes)


def test_moves_outside_the_attacker_capabilities_are_dropped() -> None:
    profile = load_profile()
    honest = profile.model_copy(
        update={
            "attacker_capabilities": profile.attacker_capabilities.model_copy(
                update={"spoof_caller_id": False, "clone_voice": False}
            )
        }
    )
    with pytest.raises(ValueError, match="capabilities"):
        red.plan(CFO, partial(new_sandbox, honest), use_llm=False)


def test_red_content_fills_in_what_only_the_replay_knows() -> None:
    move = Move(
        kind="change_request",
        at=2,
        params={
            "vendor": "V-007",
            "fields": "bank",
            "channel": "email",
            "sender": "lookalike",
            "text": red.TEMPLATES["change_request/bank"],
        },
    )
    _, sb, _ = replay_detailed(7, [move], sandbox=factory_for(None))
    (msg,) = [e.payload["message"] for e in sb.run.state.events if e.kind == "channel.received"]
    assert "{" not in msg["body"] and msg["meta"]["account"] in msg["body"]


def test_claude_reads_and_writes_when_l0_answers(monkeypatch) -> None:
    def fake(*, schema, step, **_):
        if step == "plan":
            return schema(
                moves=[
                    {
                        "kind": "change_request",
                        "at": 2,
                        "params": [
                            {"key": "vendor", "value": "V-007"},
                            {"key": "fields", "value": "bank"},
                            {"key": "channel", "value": "email"},
                            {"key": "sender", "value": "lookalike"},
                        ],
                    },
                    {
                        "kind": "change_request",
                        "at": 2,
                        "params": [
                            {"key": "vendor", "value": "V-999"},
                            {"key": "fields", "value": "bank"},
                        ],
                    },
                ],
                scenario="a",
            )
        return schema(texts=["Please use {account} from now on. {signer}"])

    monkeypatch.setattr(llm, "structured", fake)
    p = red.plan("anything", factory_for(None))
    assert p.source == "llm" and len(p.moves) == 1  # the unknown vendor was dropped
    assert any("V-999" in n or "unknown vendor" in n for n in p.notes)
    assert p.moves[0].params["text"].startswith("Please use {account}")


def test_vandal_inject_reports_controls_held_under_v3(capsys) -> None:
    assert main(["inject", CFO, "--no-llm", "--policy", "v3"]) == 0
    out = capsys.readouterr().out
    assert "It's the CFO" in out and "controls held" in out


def test_vandal_inject_composes_a_trace(capsys, tmp_path) -> None:
    trace = Trace(name="composed", moves=[change(2)])
    path = tmp_path / "t.json"
    path.write_text(trace.model_dump_json())
    assert main(["inject", "--trace", str(path), "--no-repair"]) == 1
    out = capsys.readouterr().out
    assert "threat (trace)" in out and "diagnosis: approval_binding" in out


@pytest.mark.slow
def test_vandal_inject_sends_the_violation_into_cegis(capsys) -> None:
    assert main(["inject", CFO, "--no-llm"]) == 1
    out = capsys.readouterr().out
    assert "the injected moves weren't needed" in out
    assert "repaired:" in out and "T1 VerifiedAccountChange" in out
