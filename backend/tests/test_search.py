"""R4 done-when: with no hints, `vandal search --scenario a --depth 4` finds R3's counterexample,
minimized, and prints the sequences explored and the throughput."""

from __future__ import annotations

from functools import partial
from pathlib import Path

import pytest

from vandal.cli import main
from vandal.contracts.moves import Move
from vandal.sandbox import new_sandbox
from vandal.search.alphabet import SCENARIOS, build_alphabet, independent, vendor_classes
from vandal.search.bfs import Runner, canonical_children, search
from vandal.search.minimize import ddmin, minimize_trace
from vandal.twin.profile import load_profile
from vandal.twin.seed import seed_state
from vandal.verify.replay import Trace, replay

A = SCENARIOS["a"]
FACTORY = partial(new_sandbox, "bayline")
TRACE = Path(__file__).resolve().parents[1] / "scenarios" / "a_manual.json"


@pytest.fixture(scope="module")
def found():
    return search(FACTORY, A, depth=4)


def test_vendor_classes_cover_exposure_not_the_answer() -> None:
    state, profile = seed_state(), load_profile()
    over, under = vendor_classes(state, profile)
    assert over == "V-007"  # the only vendor with an open invoice over $25k
    open_vendors = {i.vendor for i in state.invoices.values() if i.status == "received"}
    assert under in open_vendors and under != over


def _caps(profile, **changes):
    return profile.model_copy(
        update={"attacker_capabilities": profile.attacker_capabilities.model_copy(update=changes)}
    )


def test_alphabet_respects_attacker_capabilities() -> None:
    state, profile = seed_state(), load_profile()
    alphabet = build_alphabet(A, state, profile)
    # per insertion point: 2 vendors x {bank, contact} x 2 senders, 2 vendors x 2 confirmation
    # channels, and one batch trigger
    assert len(alphabet) == 5 * (2 * 2 * 2 + 2 * 2 + 1)
    assert {m.kind for m in alphabet} == {"change_request", "inbound_confirmation", "trigger_batch"}
    assert {m.params.get("channel") for m in alphabet} == {None, "email", "phone_in", "video"}
    assert len(build_alphabet(A, state, _caps(profile, senders=["lookalike"]))) == 5 * (4 + 4 + 1)
    no_fakes = _caps(profile, spoof_caller_id=False, clone_voice=False)
    assert not [m for m in build_alphabet(A, state, no_fakes) if m.kind == "inbound_confirmation"]


def test_portal_takeover_is_its_own_channel_class() -> None:
    """A portal submission is authenticated evidence on its own, so it can't share a class with
    email: with a takeover, search tries it, and it beats a T1 that accepts the portal."""
    from vandal.synth.templates import Policy

    profile = load_profile()
    caps = profile.attacker_capabilities.model_dump()
    with pytest.raises(ValueError, match="portal_takeover"):
        type(profile.attacker_capabilities).model_validate(
            caps | {"change_request_channels": ["email", "portal"]}
        )
    takeover = _caps(
        profile, change_request_channels=["email", "agent_msg", "portal"], portal_takeover=True
    )
    channels = {m.params.get("channel") for m in build_alphabet(A, seed_state(), takeover)}
    assert {"email", "portal"} <= channels and "agent_msg" not in channels
    v1 = partial(new_sandbox, takeover, policy=Policy.load(Path("policies/v1.json")))
    result = search(v1, A, depth=1)
    assert result.best is not None and result.best.moves[0].params["channel"] == "portal"


def test_search_finds_scenario_a_unaided(found) -> None:
    best = found.best
    assert best is not None and len(best.moves) == 1
    (move,) = best.moves
    assert move.kind == "change_request" and move.params["vendor"] == "V-007"
    assert move.at == 2  # after approval, before the batch: R3's trace, found not given
    assert {"INV-2", "INV-4"} <= set(best.violated)
    assert best.exposure == 4_000_000
    assert found.levels == [found.alphabet]  # stopped at the first violating depth
    assert found.explored == found.alphabet and found.seconds > 0


def test_minimizes_the_hand_written_trace() -> None:
    trace = Trace.load(TRACE)

    def run(moves):
        return set(replay(trace.seed, moves, sandbox=FACTORY, days=trace.days).violated)

    minimal = minimize_trace(trace.moves, run)
    assert [m.kind for m in minimal] == ["change_request"]
    assert {"INV-2", "INV-4"} <= run(minimal)


def test_ddmin_is_one_minimal() -> None:
    moves = [Move(kind="tick", params={"n": i}, at=i) for i in range(8)]
    needed = {2, 5}

    def violates(ms):
        return needed <= {m.params["n"] for m in ms}

    assert [m.params["n"] for m in ddmin(moves, violates)] == [2, 5]


def test_canonical_order_and_partial_order_reduction() -> None:
    cr = lambda v, at: Move(kind="change_request", at=at, params={"vendor": v})  # noqa: E731
    alphabet = [
        cr("V-1", 0),
        cr("V-2", 0),
        Move(kind="trigger_batch", at=0, params={}),
        cr("V-1", 1),
    ]
    assert independent(alphabet[0], alphabet[1])
    assert not independent(alphabet[0], alphabet[2])
    children, skipped = canonical_children((1,), alphabet)
    # V-1@0 after V-2@0 is the same as V-2@0 then V-1@0: explored once, in alphabet order.
    assert (1, 0) not in children and skipped == 1
    assert {(1, 1), (1, 2), (1, 3)} == set(children)
    children, _ = canonical_children((3,), alphabet)
    assert children == [(3, 3)]  # time never goes backwards


def test_shared_prefix_runs_match_full_runs() -> None:
    runner = Runner(FACTORY(7), A)
    alphabet = build_alphabet(A, runner.base, runner.sb.profile)
    parent = [alphabet[12]]  # trigger_batch @0
    children = [m for m in alphabet if m.at >= parent[-1].at][::7]
    shared = runner.run_children(parent, children)
    assert shared == [runner.run(parent + [c]) for c in children]


def test_workers_and_dedup_dont_change_results() -> None:
    one = search(FACTORY, A, depth=2, exhaustive=True)
    two = search(FACTORY, A, depth=2, exhaustive=True, workers=2)
    assert one.findings == two.findings and one.levels == two.levels
    assert one.deduped == two.deduped > 0 and one.pruned > 0
    assert search(FACTORY, A, depth=4).best == search(FACTORY, A, depth=4).best


def test_vandal_search_cli(capsys) -> None:
    assert main(["search", "--scenario", "a", "--depth", "4"]) == 0
    out = capsys.readouterr().out
    assert "explored          65 sequences" in out
    assert "runs/s" in out and "ms/run" in out
    assert "@2   change_request vendor=V-007" in out
    assert "VIOLATED INV-2, INV-4, INV-5  exposure $40,000.00" in out
    assert "approval.granted" in out and "vendor.bank_changed" in out
