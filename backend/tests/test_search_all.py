"""The combined "all" window: every threat family in one search, so search isn't told where to
look. It keeps going past the first violating depth until every family has a finding."""

from __future__ import annotations

from functools import partial

import pytest
from fastapi.testclient import TestClient

from vandal.api.main import app
from vandal.contracts.moves import Move
from vandal.sandbox import new_sandbox
from vandal.search.alphabet import ALL, SCENARIOS, SEARCH_SCENARIOS, build_alphabet, family_of
from vandal.search.bfs import Finding, _best_by_family, search
from vandal.synth.templates import load_policy
from vandal.twin.profile import load_profile
from vandal.twin.seed import seed_state


def _m(move_kind: str, **params) -> Move:
    return Move(kind=move_kind, at=0, params=params)


def test_all_is_the_union_of_every_family() -> None:
    assert set(ALL.kinds) == {k for s in SCENARIOS.values() for k in s.kinds}
    assert SEARCH_SCENARIOS["all"] is ALL
    assert "all" not in SCENARIOS  # Red's planner and held-out variants pick a single family
    state, profile = seed_state(), load_profile()
    combined = build_alphabet(ALL, state, profile)
    singles = [m for s in SCENARIOS.values() for m in build_alphabet(s, state, profile)]
    assert sorted(map(repr, combined)) == sorted(map(repr, singles))


def test_family_of() -> None:
    bank = _m("change_request", vendor="V-007", fields="bank", channel="email", sender="lookalike")
    assert family_of([bank, _m("trigger_batch")]) == "a"
    assert family_of([_m("fault", kind="drop_ack"), _m("retry")]) == "b"
    assert family_of([_m("deposit", customer="C-001", amount="overpay")]) == "f"
    assert family_of([bank, _m("fault", kind="drop_ack")]) == "all"  # mixed


def test_api_accepts_all() -> None:
    client = TestClient(app)
    assert client.post("/search", json={"scenario": "nope"}).status_code == 400
    job = client.post("/search", json={"scenario": "all", "depth": 1}).json()
    assert job["kind"] == "search"


def test_mixed_findings_that_contain_a_smaller_attack_dont_count() -> None:
    bank = _m("change_request", vendor="V-007", fields="bank", channel="email", sender="lookalike")
    alone = Finding(moves=[bank], violated=["INV-4"], exposure=100)
    padded = Finding(moves=[_m("retry"), bank], violated=["INV-4"], exposure=100)
    assert set(_best_by_family([alone, padded])) == {"a"}
    real = Finding(moves=[_m("retry"), bank], violated=["INV-3"], exposure=50)
    assert set(_best_by_family([real])) == {"all"}


@pytest.mark.slow
def test_one_search_finds_every_family_under_v0() -> None:
    found = search(partial(new_sandbox, "bayline"), ALL, depth=3, workers=4)
    assert set(found.by_family) == {"a", "b", "f"}  # the padded bank change isn't "mixed"
    assert found.by_family["a"].exposure > 0
    assert "INV-3" in found.by_family["b"].violated  # the double payment


@pytest.mark.slow
def test_v3_closes_every_family() -> None:
    factory = partial(new_sandbox, "bayline", policy=load_policy("v3"))
    assert search(factory, ALL, depth=2, workers=4).findings == []
