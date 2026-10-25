"""R13: Red's threat hunter. Claude studies the company and proposes attacks; the twin runs them,
and what happened goes back into the next prompt. The suite never calls Claude, so these tests
script the model's replies."""

from __future__ import annotations

import json
import time
from functools import partial

import pytest
from fastapi.testclient import TestClient

from vandal import llm
from vandal.api.main import create_app
from vandal.contracts.moves import Move
from vandal.sandbox import new_sandbox
from vandal.search.hunt import (
    HuntUnavailable,
    hunt,
    run_hypothesis,
    snapshot,
    window_for,
)

FACTORY = partial(new_sandbox, "bayline")
BANK_CHANGE = {
    "kind": "change_request",
    "at": 2,
    "params": [
        {"key": "vendor", "value": "V-007"},
        {"key": "fields", "value": "bank"},
        {"key": "channel", "value": "email"},
        {"key": "sender", "value": "lookalike"},
    ],
}


def scripted(monkeypatch, replies: list[dict]) -> list[dict]:
    """Make structured() return `replies` in order; returns the prompts it was given."""
    prompts: list[dict] = []

    def fake(*, schema, prompt, **_kw):
        prompts.append(json.loads(prompt))
        return schema.model_validate(replies[len(prompts) - 1])

    monkeypatch.setattr(llm, "structured", fake)
    return prompts


def hyp(weak_spot: str, *moves: dict) -> dict:
    return {
        "rationale": f"noticed: {weak_spot}",
        "weak_spot": weak_spot,
        "target_invariant": "INV-4",
        "moves": list(moves),
    }


def test_snapshot_is_the_company_and_never_the_oracle() -> None:
    snap = snapshot(FACTORY(7))
    assert len(snap["vendors"]) == 25 and snap["tenants"]
    assert any(v["open_invoices"] for v in snap["vendors"])
    assert snap["active_controls"] and snap["attacker_profile"]
    assert "oracle" not in json.dumps(snap).lower()


def test_run_hypothesis_reports_what_broke_and_what_guard_did() -> None:
    m = Move.model_validate(
        {**BANK_CHANGE, "params": {p["key"]: p["value"] for p in BANK_CHANGE["params"]}}
    )
    _, out = run_hypothesis([m], 7, FACTORY)
    assert {"INV-2", "INV-4"} <= set(out.violated) and out.exposure == 4_000_000
    assert any("approval.threshold" in g for g in out.guard)  # Guard escalated the $40k invoice


def test_moves_the_twin_cant_run_are_dropped_with_a_reason() -> None:
    bad = Move(kind="change_request", at=2, params={"vendor": "V-999", "fields": "bank"})
    ran, out = run_hypothesis([bad], 7, FACTORY)
    assert ran == [] and out.dropped and "V-999" in out.dropped[0]


def test_the_loop_feeds_each_outcome_into_the_next_prompt(monkeypatch) -> None:
    prompts = scripted(
        monkeypatch,
        [
            hyp(
                "an unknown vendor",
                {**BANK_CHANGE, "params": [{"key": "vendor", "value": "V-999"}]},
            ),
            hyp("approval reads the current account", BANK_CHANGE),
        ],
    )
    seen = []
    r = hunt(FACTORY, attempts=4, on_attempt=seen.append)
    assert [a.n for a in seen] == [1, 2] and r.hits == 1
    assert prompts[0]["earlier_attempts"] == []
    first = prompts[1]["earlier_attempts"][0]
    assert first["weak_spot"] == "an unknown vendor" and first["outcome"]["dropped"]
    assert r.best and set(r.best.violated) >= {"INV-4"} and r.best.attempt == 2
    assert len(r.best.moves) == 1  # minimized
    assert r.best.outside_preset_search is False  # this one is in Scenario A's alphabet


def test_novelty_is_measured_against_the_preset_alphabets(monkeypatch) -> None:
    off_grid = {**BANK_CHANGE, "at": 7}  # day 1: outside Scenario A's one-day window
    scripted(monkeypatch, [hyp("late change", off_grid)])
    r = hunt(FACTORY, attempts=1)
    if r.best:  # whether a day-1 change still lands depends on the World; novelty must match
        assert r.best.outside_preset_search is bool(r.best.novel_moves)


def test_no_claude_no_hunt() -> None:
    with pytest.raises(HuntUnavailable):
        hunt(FACTORY, attempts=1)


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
    scripted(monkeypatch, [hyp("approval reads the current account", BANK_CHANGE)])
    with TestClient(create_app(persist=False)) as client:
        run = client.post("/runs", json={"policy": "v0"}).json()
        job = client.post(f"/runs/{run['run_id']}/hunt", json={"attempts": 2}).json()
        assert job["kind"] == "hunt"
        deadline = time.monotonic() + 60
        while (done := client.get(f"/jobs/{job['id']}").json())["status"] not in ("done", "failed"):
            assert time.monotonic() < deadline
            time.sleep(0.05)
        assert done["status"] == "done", done.get("error")
        assert done["result"]["best"]["exposure"] == 4_000_000
        d = client.post("/diagnose", json={"search_id": job["id"]}).json()
        assert d["diagnosis"]["gap"] == "approval_binding"


def test_a_bill_red_sends_is_booked_as_a_duplicate_by_the_harness() -> None:
    """Claude's first live finding: a near-duplicate bill for a vendor with no PO is paid twice,
    under every policy through v3. The harness, not the model, says the bill isn't owed."""
    from vandal.synth.templates import load_policy

    clone = Move(
        kind="submit_invoice",
        at=0,
        params={"vendor": "V-014", "number": "MOR14-1722B", "amount": 749_700, "due_in_days": 2},
    )
    v3 = partial(new_sandbox, "bayline", policy=load_policy("v3"))
    _, out = run_hypothesis([clone], 7, v3)
    assert out.violated == ["INV-3"] and out.exposure == 749_700
    assert "duplicates INV-1058" in out.violations[0]
