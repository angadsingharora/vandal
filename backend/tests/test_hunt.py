"""R13: the hunt. Attacks come from a written playbook, in its order; the twin runs them, and
everything about the outcome comes from the simulation. No model is involved."""

from __future__ import annotations

import json
import random
import time
from functools import partial

import pytest
from fastapi.testclient import TestClient

from vandal.api.main import create_app
from vandal.contracts.moves import Move
from vandal.sandbox import new_sandbox
from vandal.search.hunt import PLAYBOOK, hunt, run_hypothesis, snapshot, window_for
from vandal.synth.templates import load_policy

FACTORY = partial(new_sandbox, "bayline")
BANK_CHANGE = Move(
    kind="change_request",
    at=2,
    params={"vendor": "V-007", "fields": "bank", "channel": "email", "sender": "lookalike"},
)
BREAKS = [h for h in PLAYBOOK if h.breaks]
HOLDS = [h for h in PLAYBOOK if not h.breaks]


def test_snapshot_is_the_company_and_never_the_oracle() -> None:
    snap = snapshot(FACTORY(7))
    assert len(snap["vendors"]) == 25 and snap["tenants"]
    assert any(v["open_invoices"] for v in snap["vendors"])
    assert snap["active_controls"] and snap["attacker_profile"]
    assert "oracle" not in json.dumps(snap).lower()


def test_run_hypothesis_reports_what_broke_and_what_guard_did() -> None:
    _, out = run_hypothesis([BANK_CHANGE], 7, FACTORY)
    assert {"INV-2", "INV-4"} <= set(out.violated) and out.exposure == 4_000_000
    assert any("approval.threshold" in g for g in out.guard)  # Guard escalated the $40k invoice


def test_moves_the_twin_cant_run_are_dropped_with_a_reason() -> None:
    bad = Move(kind="change_request", at=2, params={"vendor": "V-999", "fields": "bank"})
    ran, out = run_hypothesis([bad], 7, FACTORY)
    assert ran == [] and out.dropped and "V-999" in out.dropped[0]


def test_the_playbook_is_half_misses_half_hits() -> None:
    assert len(PLAYBOOK) == 6 and len(BREAKS) == 3 and len(HOLDS) == 3
    assert PLAYBOOK[2].moves[0].kind == "change_request"  # the demo's story, after two misses


@pytest.mark.parametrize("hyp", PLAYBOOK, ids=lambda h: h.weak_spot[:28])
def test_every_playbook_entry_does_what_it_says_under_v0(hyp) -> None:
    """The playbook is canned; the outcome is not. An entry marked `breaks` must still break
    the invariant it names at the seeded books, and one marked safe must still come up safe,
    or the hunt the audience sees would not match the story."""
    ran, out = run_hypothesis(hyp.moves, 7, FACTORY)
    assert ran and not out.dropped, (hyp.weak_spot, out.dropped)
    if hyp.breaks:
        assert hyp.target_invariant in out.violated and out.exposure > 0, (hyp.weak_spot, out)
    else:
        assert out.violated == [] and out.exposure == 0, (hyp.weak_spot, out)


def test_the_hunt_is_deterministic_and_runs_every_attempt() -> None:
    """The demo lands on the same attack, and so the same fix, every time: six attempts, three
    held, three broke, and the best is the $40,000 bank change (attempt 3)."""
    seen = []
    r = hunt(FACTORY, attempts=6, keep_going=True, on_attempt=seen.append, pause=0)
    assert [a.n for a in seen] == [1, 2, 3, 4, 5, 6]
    assert [bool(a.outcome.violated) for a in seen] == [h.breaks for h in PLAYBOOK]
    assert r.hits == 3 and r.reason == "3 of 6 attempts broke an invariant"
    assert r.best and r.best.attempt == 3 and r.best.violated == ["INV-2", "INV-4", "INV-5"]
    assert r.best.exposure == 4_000_000 and len(r.best.moves) == 1  # minimized
    again = hunt(FACTORY, attempts=6, keep_going=True, pause=0)
    assert again.model_dump() == r.model_dump()


def test_without_keep_going_the_hunt_stops_at_the_first_hit() -> None:
    r = hunt(FACTORY, attempts=6, pause=0)
    assert len(r.attempts) == 3 and r.hits == 1 and r.reason.startswith("attempt 3 broke")


def test_an_rng_shuffles_the_playbook_and_never_repeats_an_entry() -> None:
    first = {
        hunt(FACTORY, attempts=1, keep_going=True, pause=0, rng=random.Random(s))
        .attempts[0]
        .weak_spot
        for s in range(8)
    }
    assert len(first) > 1
    r = hunt(FACTORY, attempts=12, keep_going=True, pause=0, rng=random.Random(1))
    spots = [a.weak_spot for a in r.attempts]
    assert len(spots) == len(PLAYBOOK) == len(set(spots))
    assert r.hits == 3 and r.best.exposure == 4_000_000  # the costliest hit wins


def test_the_hunt_pauses_before_each_attempt() -> None:
    t = time.monotonic()
    hunt(FACTORY, attempts=1, pause=0.3)
    assert time.monotonic() - t >= 0.3


def test_under_a_stronger_policy_the_twin_decides() -> None:
    """The same playbook against v3: whether an entry still lands is the twin's call. The
    bank change is held, and the hunt reports it as held rather than asserting a hit."""
    v3 = partial(new_sandbox, "bayline", policy=load_policy("v3"))
    r = hunt(v3, attempts=12, keep_going=True, pause=0)
    bank = r.attempts[2]
    assert bank.moves[0].kind == "change_request" and not bank.outcome.violated
    assert bank.outcome.guard


def test_window_for_picks_the_family() -> None:
    assert (
        window_for(
            [Move(kind="deposit", at=0, params={}), Move(kind="refund_request", at=1, params={})]
        )
        == "f"
    )
    assert (
        window_for([Move(kind="fault", at=0, params={}), Move(kind="retry", at=1, params={})])
        == "b"
    )


def test_api_hunt_then_diagnose(monkeypatch) -> None:
    monkeypatch.setenv("VANDAL_HUNT_PAUSE", "0")
    with TestClient(create_app(persist=False)) as client:
        run = client.post("/runs", json={"policy": "v0"}).json()
        body = {"attempts": 6, "keep_going": True}  # what the war room sends
        job = client.post(f"/runs/{run['run_id']}/hunt", json=body).json()
        assert job["kind"] == "hunt"
        deadline = time.monotonic() + 90
        while (done := client.get(f"/jobs/{job['id']}").json())["status"] not in ("done", "failed"):
            assert time.monotonic() < deadline
            time.sleep(0.05)
        assert done["status"] == "done", done.get("error")
        assert done["result"]["hits"] == 3 and len(done["result"]["attempts"]) == 6
        assert done["result"]["best"]["exposure"] == 4_000_000
        assert done["result"]["scenario"] == "a"
        d = client.post("/diagnose", json={"search_id": job["id"]}).json()
        assert d["diagnosis"]["gap"] == "approval_binding"


def test_a_bill_red_sends_is_booked_as_a_duplicate_by_the_harness() -> None:
    """A near-duplicate bill for a vendor with no PO is paid twice, under every policy through
    v3. The harness, not the hypothesis, says the bill isn't owed."""
    clone = Move(
        kind="submit_invoice",
        at=0,
        params={"vendor": "V-014", "number": "MOR14-1722B", "amount": 749_700, "due_in_days": 2},
    )
    v3 = partial(new_sandbox, "bayline", policy=load_policy("v3"))
    _, out = run_hypothesis([clone], 7, v3)
    assert out.violated == ["INV-3"] and out.exposure == 749_700
    assert "duplicates INV-1058" in out.violations[0]
