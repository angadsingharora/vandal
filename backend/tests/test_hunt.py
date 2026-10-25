"""R13: the hunt. Attacks come from a written playbook, in a random order; the twin runs them,
and everything about the outcome comes from the simulation. No model is involved."""

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


@pytest.mark.parametrize("hyp", PLAYBOOK, ids=lambda h: h.target_invariant)
def test_every_playbook_entry_breaks_v0_in_the_twin(hyp) -> None:
    """The playbook is canned; whether it works is not. Each entry must still break the
    invariant it names at the seeded books, or the demo would show a hunt that finds nothing."""
    ran, out = run_hypothesis(hyp.moves, 7, FACTORY)
    assert ran and not out.dropped, (hyp.weak_spot, out.dropped)
    assert hyp.target_invariant in out.violated and out.exposure > 0, (hyp.weak_spot, out)


def test_the_hunt_picks_an_entry_and_stops_at_the_first_hit() -> None:
    seen = []
    r = hunt(FACTORY, attempts=4, on_attempt=seen.append, pause=0, rng=random.Random(3))
    assert [a.n for a in seen] == [1] and r.hits == 1
    assert r.best and r.best.attempt == 1 and r.best.violated
    assert len(r.best.moves) <= len(seen[0].moves)  # minimized
    assert seen[0].rationale and seen[0].weak_spot in {h.weak_spot for h in PLAYBOOK}
    assert r.reason.startswith("attempt 1 broke")


def test_the_order_is_random_and_never_repeats_an_entry() -> None:
    first = {
        hunt(FACTORY, attempts=1, pause=0, rng=random.Random(s)).attempts[0].weak_spot
        for s in range(8)
    }
    assert len(first) > 1
    r = hunt(FACTORY, attempts=12, keep_going=True, pause=0, rng=random.Random(1))
    spots = [a.weak_spot for a in r.attempts]
    assert len(spots) == len(PLAYBOOK) == len(set(spots))
    assert r.hits == len(PLAYBOOK)
    assert r.reason == f"{r.hits} of {len(PLAYBOOK)} attempts broke an invariant"
    assert r.best.exposure == 4_000_000  # the costliest hit wins
    assert r.best.outside_preset_search is False  # bank change or lost ack: both in a family


def test_the_hunt_pauses_before_each_attempt() -> None:
    t = time.monotonic()
    hunt(FACTORY, attempts=1, pause=0.3, rng=random.Random(0))
    assert time.monotonic() - t >= 0.3


def test_under_a_stronger_policy_the_twin_decides() -> None:
    """The same playbook against v3: whether an entry still lands is the twin's call, and the
    hunt reports a miss as held rather than asserting a hit."""
    v3 = partial(new_sandbox, "bayline", policy=load_policy("v3"))
    r = hunt(v3, attempts=12, keep_going=True, pause=0, rng=random.Random(0))
    held = [a for a in r.attempts if not a.outcome.violated]
    assert held, "v3 should stop at least one playbook entry"
    assert all(a.outcome.guard for a in held)


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
        job = client.post(f"/runs/{run['run_id']}/hunt", json={"attempts": 2}).json()
        assert job["kind"] == "hunt"
        deadline = time.monotonic() + 60
        while (done := client.get(f"/jobs/{job['id']}").json())["status"] not in ("done", "failed"):
            assert time.monotonic() < deadline
            time.sleep(0.05)
        assert done["status"] == "done", done.get("error")
        best = done["result"]["best"]
        assert best and best["exposure"] > 0 and best["violated"]
        assert done["result"]["scenario"] in ("a", "b", "f")
        d = client.post("/diagnose", json={"search_id": job["id"]}).json()
        assert d["diagnosis"]["gap"]


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
