"""What a public host needs from the API: limits it can set (api/limits.py), a 429 when it is
busy, recorded jobs served instantly under playback (api/jobcache.py), an evidence pack a
reviewer can download, and a /health a monitor can read."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from vandal.api.main import create_app

from .test_api import wait


def make(monkeypatch: pytest.MonkeyPatch, **env: str) -> TestClient:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return TestClient(create_app(persist=False))


def test_health_and_settings_report_the_host(monkeypatch) -> None:
    with make(monkeypatch, VANDAL_MAX_DEPTH="2", VANDAL_MAX_JOBS="3", SEARCH_WORKERS="2") as c:
        health = c.get("/health").json()
        assert health["status"] == "ok"
        assert health["version"]
        assert health["uptime_s"] >= 0
        assert health["jobs_active"] == 0
        assert health["limits"] == {
            "max_depth": 2,
            "max_workers": 32,
            "max_jobs": 3,
            "jobs_per_client": 0,
            "max_runs": 0,
            "default_workers": 2,
        }
        assert c.get("/settings").json()["limits"]["max_depth"] == 2


def test_depth_and_workers_are_clamped_to_the_host(monkeypatch) -> None:
    with make(monkeypatch, VANDAL_MAX_DEPTH="1", VANDAL_MAX_WORKERS="2") as c:
        job = c.post("/search", json={"depth": 4, "workers": 16}).json()
        assert job["meta"]["depth"] == 1
        assert job["meta"]["workers"] == 2
        assert job["meta"]["clamped"] is True
        assert wait(c, job["id"])["result"]["depth"] == 1
        # metrics clamp too: the page stays interactive on a small host
        assert c.get("/metrics?policies=v0&depth=3").json()["depth"] == 1


def test_a_busy_host_answers_429(monkeypatch) -> None:
    with make(monkeypatch, VANDAL_MAX_JOBS="1") as c:
        first = c.post("/search", json={"depth": 3}).json()
        busy = c.post("/search", json={"depth": 1})
        assert busy.status_code == 429
        assert busy.headers["retry-after"] == "30"
        assert "busy" in busy.json()["detail"]
        wait(c, first["id"])
        # once it finishes, the next job is accepted (and waited for, so it records into the
        # test's cache, not the repo's)
        accepted = c.post("/search", json={"depth": 1})
        assert accepted.status_code == 200
        wait(c, accepted.json()["id"])


def test_finished_jobs_are_kept_to_a_bound(monkeypatch) -> None:
    with make(monkeypatch) as c:
        c.app.state.registry.keep_finished = 2
        ids = [wait(c, c.post("/search", json={"depth": 0}).json()["id"])["id"] for _ in range(4)]
        assert c.get(f"/jobs/{ids[0]}").status_code == 404  # evicted at the 4th submit
        assert c.get(f"/jobs/{ids[-1]}").status_code == 200


def test_recorded_jobs_replay_under_playback(monkeypatch, tmp_path) -> None:
    cache = tmp_path / "job_cache"
    with make(monkeypatch, JOB_CACHE_DIR=str(cache), DEMO_PLAYBACK="true") as c:
        body = {"depth": 1, "scenario": "a"}
        first = wait(c, c.post("/search", json=body).json()["id"])["result"]
        assert first["cached"] is False
        assert len(list(cache.glob("jobs-v1.search.*.json"))) == 1

        job = c.post("/search", json=body).json()
        again = wait(c, job["id"])
        assert again["result"]["cached"] is True
        assert again["result"]["recorded_at"]
        assert again["result"]["explored"] == first["explored"]
        # the stream a page follows still gets its progress, then done
        with c.stream("GET", f"/jobs/{job['id']}/events?follow=false") as resp:
            text = "".join(resp.iter_text())
        assert "event: progress" in text and "event: done" in text

        fresh = wait(c, c.post("/search", json={**body, "fresh": True}).json()["id"])["result"]
        assert fresh["cached"] is False
        # a different depth is a different recording
        assert (
            wait(c, c.post("/search", json={"depth": 0}).json()["id"])["result"]["cached"] is False
        )

    # playback off: the recording is there, and still not served
    with make(monkeypatch, JOB_CACHE_DIR=str(cache), DEMO_PLAYBACK="false") as c:
        out = wait(c, c.post("/search", json=body).json()["id"])["result"]
        assert out["cached"] is False


@pytest.mark.slow
def test_evidence_pack_downloads(monkeypatch) -> None:
    with make(monkeypatch) as c:
        job = c.post("/verify", json={"policy": "v1", "depth": 1}).json()
        assert c.get(f"/jobs/{job['id']}/evidence").status_code == 409  # not done yet
        wait(c, job["id"])
        resp = c.get(f"/jobs/{job['id']}/evidence")
        assert resp.status_code == 200
        assert (
            resp.headers["content-disposition"] == 'attachment; filename="vandal-evidence-v1.json"'
        )
        assert resp.json()["version"] == "v1"
        search = c.post("/search", json={"depth": 0}).json()
        wait(c, search["id"])
        assert c.get(f"/jobs/{search['id']}/evidence").status_code == 400  # not a verify job
