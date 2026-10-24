"""The routes the war room (F0-F6) reads beyond A0's: the twin's tables, oracle labels for the
Judge view, applied policies in replay and search, inject over the API (R9), and the playback
switch."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_api import wait
from vandal.api.main import create_app
from vandal.synth.templates import load_policy
from vandal.verify.replay import Trace

TRACE = Trace.load(Path(__file__).resolve().parents[1] / "scenarios" / "a_manual.json")
MOVES = [m.model_dump() for m in TRACE.moves]


@pytest.fixture
def client():
    with TestClient(create_app(persist=False)) as c:
        yield c


def test_entities_show_the_misdirected_payment_and_the_answer_key(client) -> None:
    run = client.post("/replay", json={"moves": MOVES, "days": TRACE.days}).json()
    assert any(lb["label"] == "attacker_controlled" for lb in run["labels"])
    t = client.get(f"/runs/{run['run']['run_id']}/entities").json()
    assert t["totals"]["exposure"] == 4_000_000
    pay = next(p for p in t["payments"] if p["id"] == "PAY-0057")
    assert pay["invoice"] == "INV-1042" and pay["amount"] == 4_000_000
    attacker = next(a for a in t["vendor_bank_accounts"] if a["id"] == pay["payee_account"])
    assert attacker["status"] == "unverified"
    assert t["labels"] == run["labels"]
    violated = {
        v["invariant"]
        for v in client.get(f"/runs/{run['run']['run_id']}/state").json()["violations"]
    }
    assert violated == set(run["result"]["violated"])  # INV-4 included, from the labels
    assert len(t["invoices"]) == 80 and t["bank_accounts"]


def test_a_fresh_run_has_no_labels(client) -> None:
    run = client.post("/runs").json()
    t = client.get(f"/runs/{run['run_id']}/entities").json()
    assert t["labels"] == [] and t["totals"]["exposure"] == 0 and t["totals"]["cash"] > 0


def test_replay_and_search_use_policies_applied_through_the_inbox(client) -> None:
    v1 = load_policy("v1")
    client.app.state.registry.applied["v1-synth"] = v1.model_copy(update={"version": "v1-synth"})
    assert "v1-synth" in [p["name"] for p in client.get("/policies").json()]
    assert client.get("/policies/v1-synth").json()["version"] == "v1-synth"
    held = client.post("/replay", json={"moves": MOVES, "policy": "v1-synth"}).json()
    assert held["run"]["policy"] == "v1-synth" and held["result"]["violations"] == []
    job = client.post("/search", json={"policy": "v1-synth", "depth": 0}).json()
    assert wait(client, job["id"])["status"] == "done"


def test_inject_dry_run_reads_plain_language(client) -> None:
    run = client.post("/runs").json()["run_id"]
    body = {
        "description": "the CFO calls from an airport asking for an urgent wire to a new supplier",
        "no_llm": True,
        "dry_run": True,
    }
    plan = client.post(f"/runs/{run}/inject", json=body).json()["plan"]
    assert [m["kind"] for m in plan["moves"]] == ["message"] and plan["source"] == "keywords"


def test_inject_composed_moves_then_diagnose_and_its_errors(client) -> None:
    run = client.post("/runs").json()["run_id"]
    job = client.post(f"/runs/{run}/inject", json={"moves": MOVES}).json()
    done = wait(client, job["id"])
    assert done["status"] == "done", done["error"]
    assert done["result"]["best"]["exposure"] == 4_000_000 and done["result"]["needed"]
    d = client.post("/diagnose", json={"search_id": job["id"]}).json()["diagnosis"]
    assert d["gap"] == "approval_binding"
    assert client.post(f"/runs/{run}/inject", json={}).status_code == 400
    assert (
        client.post(f"/runs/{run}/inject", json={"moves": MOVES, "scenario": "z"}).status_code
        == 400
    )
    assert client.post("/runs/run-nope/inject", json={"moves": MOVES}).status_code == 404


def test_playback_switch(client, monkeypatch) -> None:
    monkeypatch.delenv("DEMO_PLAYBACK", raising=False)
    assert client.get("/settings").json()["playback"] is False
    assert client.post("/settings", json={"playback": True}).json()["playback"] is True
    assert client.get("/settings").json()["playback"] is True
    client.post("/settings", json={"playback": False})
