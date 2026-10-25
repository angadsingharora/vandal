"""A0 done-when: a client (the frontend) can create a run and stream its events against the
real backend. Plus each slice's routes, persistence through the API, and SSE resume."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vandal.api.db import Store
from vandal.api.main import create_app
from vandal.verify.replay import Trace

TRACE = Path(__file__).resolve().parents[1] / "scenarios" / "a_manual.json"


@pytest.fixture
def client():
    with TestClient(create_app(persist=False)) as c:
        yield c


def sse_messages(lines):
    """Parse SSE lines into (id, event, data) tuples."""
    msg: dict = {}
    for line in lines:
        if not line:
            if "data" in msg:
                yield int(msg["id"]), msg["event"], json.loads(msg["data"])
            msg = {}
        elif not line.startswith(":"):
            key, _, value = line.partition(": ")
            msg[key] = value


def wait(client, job_id: str, timeout: float = 120.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.05)
    raise TimeoutError(job_id)


def test_health(client) -> None:
    assert client.get("/health").json()["status"] == "ok"


def test_create_a_run_and_stream_its_events_live(client) -> None:
    run = client.post("/runs", json={"policy": "v0"}).json()
    assert run["invoices"] == {"received": 24, "paid": 56} and run["events"] == 0
    job = client.post(f"/runs/{run['run_id']}/operate", json={"days": 5}).json()
    seen = []
    with client.stream("GET", f"/runs/{run['run_id']}/events") as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        for mid, kind, data in sse_messages(resp.iter_lines()):
            assert kind == "event" and data["seq"] == mid
            seen.append(data)
            if data["kind"] == "clock.tick" and data["day"] == 4:
                break  # day 5 has started: the operate job's last event
    assert wait(client, job["id"])["status"] == "done"
    state = client.get(f"/runs/{run['run_id']}/state").json()
    assert len(seen) == state["events"] and state["invoices"] == {"paid": 80}
    assert state["violations"] == [] and state["day"] == 5


def test_resume_with_last_event_id(client) -> None:
    run = client.post("/runs").json()
    wait(client, client.post(f"/runs/{run['run_id']}/operate", json={"days": 1}).json()["id"])
    url = f"/runs/{run['run_id']}/events?follow=false"
    with client.stream("GET", url, headers={"Last-Event-ID": "9"}) as resp:
        ids = [mid for mid, _, _ in sse_messages(resp.iter_lines())]
    assert ids[0] == 10 and ids == list(range(10, 10 + len(ids)))


def test_operate_progress_streams_on_the_job(client) -> None:
    run = client.post("/runs").json()
    job = client.post(f"/runs/{run['run_id']}/operate", json={"days": 2}).json()
    with client.stream("GET", f"/jobs/{job['id']}/events") as resp:
        kinds = [(k, d) for _, k, d in sse_messages(resp.iter_lines())]
    assert [d["day"] for k, d in kinds if k == "progress"] == [1, 2]
    assert kinds[-1][0] == "done"  # the stream ends when the job does


def test_chain_ledger_and_replay(client) -> None:
    trace = Trace.load(TRACE)
    body = {"moves": [m.model_dump() for m in trace.moves], "days": trace.days}
    attacked = client.post("/replay", json=body).json()
    assert attacked["result"]["violated"] == ["INV-2", "INV-4", "INV-5"]
    run_id = attacked["run"]["run_id"]
    chain = client.get(f"/runs/{run_id}/chain/PAY-0057").json()
    execution = next(ln for ln in chain["links"] if ln["name"] == "execution")
    assert execution["gap"] == "approval_binding"
    assert client.get(f"/runs/{run_id}/ledger").json()[0]["memo"] == "Opening balances"
    held = client.post("/replay", json={**body, "policy": "v1"}).json()
    assert held["result"]["violations"] == []


def test_search_then_diagnose(client) -> None:
    job = client.post("/search", json={"policy": "v0", "depth": 2}).json()
    done = wait(client, job["id"])
    assert done["status"] == "done" and done["result"]["best"]["exposure"] == 4_000_000
    d = client.post("/diagnose", json={"search_id": job["id"]}).json()["diagnosis"]
    assert d["gap"] == "approval_binding"


def test_policies(client) -> None:
    names = {p["name"] for p in client.get("/policies").json()}
    assert {"v0", "v1"} <= names
    v1 = client.get("/policies/v1").json()
    assert [c.split()[0] for c in v1["described"]] == ["T1", "T2"]


def test_errors(client) -> None:
    assert client.get("/runs/run-nope/state").status_code == 404
    assert client.post("/runs", json={"policy": "v99"}).status_code == 400
    assert client.post("/runs", json={"policy": "policies/v1.json"}).status_code == 400
    assert client.post("/diagnose", json={"search_id": "search-nope"}).status_code == 404


def test_demo_reset_drops_runs(client) -> None:
    client.post("/runs")
    client.post("/runs")
    fresh = client.post("/demo/reset").json()
    assert [r["run_id"] for r in client.get("/runs").json()] == [fresh["run_id"]]


def test_cors_for_the_frontend(client) -> None:
    r = client.options(
        "/runs",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
    )
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_runs_persist_through_the_api(tmp_path) -> None:
    store = Store(f"sqlite:///{tmp_path / 'api.db'}")
    store.migrate()
    with TestClient(create_app(store=store)) as client:
        run = client.post("/runs").json()
        wait(client, client.post(f"/runs/{run['run_id']}/operate", json={"days": 2}).json()["id"])
        state = client.get(f"/runs/{run['run_id']}/state").json()
        assert client.get("/health").json()["persistence"] == "sqlite"
    assert store.rebuild(run["run_id"]).state_hash() == state["state_hash"]


@pytest.mark.slow
def test_search_synthesize_verify(client) -> None:
    search = client.post("/search", json={"policy": "v0", "depth": 2}).json()
    wait(client, search["id"])
    synth = client.post(
        "/synthesize", json={"search_id": search["id"], "no_llm": True, "depth": 2, "workers": 4}
    ).json()
    with client.stream("GET", f"/jobs/{synth['id']}/events") as resp:
        logs = [d for _, k, d in sse_messages(resp.iter_lines()) if k == "log"]
    result = wait(client, synth["id"])["result"]
    assert result["status"] == "repaired" and len(logs) == len(result["log"])
    verify = client.post("/verify", json={"synthesis_id": synth["id"], "depth": 1}).json()
    pack = wait(client, verify["id"], timeout=300)["result"]
    assert pack["approvable"] and pack["candidates"][0]["source"].startswith("cegis")


@pytest.mark.slow
def test_metrics(client) -> None:
    m = client.get("/metrics", params={"policies": "v0,v1", "depth": 1}).json()
    assert m["scorecards"]["v0"]["attack_success_rate"] == 1.0
    assert m["scorecards"]["v1"]["attack_success_rate"] == 0.0


def test_llm_operator_reads_a_delivered_document(client) -> None:
    """O1 in the war room: a run lists the planted documents, and delivering one makes the LLM
    Operator's intake read it and Blue gate the receive."""
    run = client.post("/runs", json={"policy": "v0"}).json()
    docs = client.get(f"/runs/{run['run_id']}/documents").json()
    assert len(docs) == 24 and {d["format"] for d in docs} == {
        "email_body",
        "ocr_text",
        "forwarded_thread",
        "line_items",
    }
    assert not any(d["delivered"] for d in docs)
    out = client.post(f"/runs/{run['run_id']}/documents/{docs[0]['id']}/deliver").json()
    assert out["extraction"]["intent"] == "invoice"
    assert out["extraction"]["number"] in docs[0]["subject"] + docs[0]["body"]
    assert out["invoice"]["number"] == out["extraction"]["number"]
    assert [(v["tool"], v["decision"]) for v in out["verdicts"]] == [("invoices.receive", "allow")]
    reads = client.get(f"/runs/{run['run_id']}/intake").json()
    assert [r["message"] for r in reads] == [docs[0]["id"]]
    assert client.get(f"/runs/{run['run_id']}/documents").json()[0]["delivered"]
    assert (
        client.post(f"/runs/{run['run_id']}/documents/{docs[0]['id']}/deliver").status_code == 409
    )


def test_search_all_families_lands_on_the_costliest_break(client) -> None:
    """One strike, every threat family (the war room's default): the merged result names the
    family its best finding came from, so diagnosis repairs it in the right window."""
    job = client.post("/search", json={"policy": "v0", "scenario": "all", "depth": 2}).json()
    done = wait(client, job["id"])
    r = done["result"]
    assert done["status"] == "done" and r["families"] == ["a", "b", "f"]
    assert r["best"]["exposure"] == 4_000_000 and r["scenario"] == "a"
    assert {v for f in r["findings"] for v in f["violated"]} >= {"INV-2", "INV-3", "INV-11"}
    d = client.post("/diagnose", json={"search_id": job["id"]}).json()["diagnosis"]
    assert d["gap"] == "approval_binding"


def test_verify_defaults_to_one_search_process_per_core(monkeypatch) -> None:
    """Verify's checks are full searches; with no `workers` in the request it uses
    SEARCH_WORKERS, else one process per core up to 8. Fix stays on one process."""
    from vandal.api.routes_jobs import SynthesizeRequest, VerifyRequest, default_workers

    assert VerifyRequest().workers is None and SynthesizeRequest().workers == 1
    monkeypatch.setenv("SEARCH_WORKERS", "3")
    assert default_workers() == 3
    monkeypatch.delenv("SEARCH_WORKERS")
    monkeypatch.setattr("os.cpu_count", lambda: 16)
    assert default_workers() == 8
    monkeypatch.setattr("os.cpu_count", lambda: None)
    assert default_workers() == 1
