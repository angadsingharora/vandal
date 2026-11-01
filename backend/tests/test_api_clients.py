"""One process, many visitors: runs belong to the client that made them, a reset drops only that
client's runs, the host bounds the runs it keeps and the jobs one client may have running."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from vandal.api.main import create_app

from .test_api import wait


def make(monkeypatch: pytest.MonkeyPatch, **env: str) -> TestClient:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return TestClient(create_app(persist=False))


def as_client(name: str) -> dict[str, str]:
    return {"X-Vandal-Client": name}


def test_a_reset_drops_only_the_callers_runs(monkeypatch) -> None:
    with make(monkeypatch) as c:
        alice = c.post("/demo/reset", headers=as_client("alice")).json()["run_id"]
        bob = c.post("/demo/reset", headers=as_client("bob")).json()["run_id"]
        # each sees only their own
        assert [r["run_id"] for r in c.get("/runs", headers=as_client("alice")).json()] == [alice]
        assert [r["run_id"] for r in c.get("/runs", headers=as_client("bob")).json()] == [bob]
        # bob starting over leaves alice's run where it was
        bob2 = c.post("/demo/reset", headers=as_client("bob")).json()["run_id"]
        assert c.get(f"/runs/{alice}/state").status_code == 200
        assert c.get(f"/runs/{bob}/state").status_code == 404
        assert [r["run_id"] for r in c.get("/runs", headers=as_client("bob")).json()] == [bob2]
        # a bare caller sees everything, and its reset drops everything (the old behaviour)
        assert len(c.get("/runs").json()) == 2
        c.post("/demo/reset")
        assert c.get(f"/runs/{alice}/state").status_code == 404


def test_the_listing_says_what_each_run_is(monkeypatch) -> None:
    with make(monkeypatch) as c:
        live = c.post("/runs", headers=as_client("alice")).json()
        rows = c.get("/runs", headers=as_client("alice")).json()
        assert rows[0] == {
            "run_id": live["run_id"],
            "kind": "operate",
            "profile": "bayline",
            "company": "Bayline Property Group",
            "seed": 7,
            "policy": "v0",
            "day": 0,
            "events": 0,
        }


def test_the_host_keeps_only_so_many_runs(monkeypatch) -> None:
    with make(monkeypatch, VANDAL_MAX_RUNS="2") as c:
        first = c.post("/runs").json()["run_id"]
        second = c.post("/runs").json()["run_id"]
        # reading the first makes it the most recently touched
        c.get(f"/runs/{first}/state")
        third = c.post("/runs").json()["run_id"]
        ids = {r["run_id"] for r in c.get("/runs").json()}
        assert ids == {first, third}
        assert c.get(f"/runs/{second}/state").status_code == 404
        assert c.get("/health").json()["runs"] == 2


def test_one_client_gets_only_so_many_jobs(monkeypatch) -> None:
    with make(monkeypatch, VANDAL_JOBS_PER_CLIENT="1") as c:
        first = c.post("/search", json={"depth": 3}, headers=as_client("alice")).json()
        again = c.post("/search", json={"depth": 1}, headers=as_client("alice"))
        assert again.status_code == 429
        assert "already have" in again.json()["detail"]
        # another client is not held back by alice's job
        other = c.post("/search", json={"depth": 1}, headers=as_client("bob"))
        assert other.status_code == 200
        wait(c, first["id"])
        wait(c, other.json()["id"])
        accepted = c.post("/search", json={"depth": 1}, headers=as_client("alice"))
        assert accepted.status_code == 200
        wait(c, accepted.json()["id"])


def test_approvals_are_scoped_to_the_caller(monkeypatch) -> None:
    with make(monkeypatch) as c:
        c.post("/demo/reset", headers=as_client("alice"))
        c.post("/demo/reset", headers=as_client("bob"))
        # nothing pending yet for anyone, but the call is scoped and answers
        assert c.get("/approvals", headers=as_client("alice")).json()["payments"] == []
