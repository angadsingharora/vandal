"""Record the mock API's fixtures from the real backend, so the mock (F0) has the same shapes.

    cd frontend && uv run --project ../backend python scripts/capture_fixtures.py

Runs the demo loop once in process (reset, operate, search, diagnose, synthesize, verify, the
inbox, replay before and after, inject, metrics) and writes src/mock/fixtures.json.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from vandal.api.main import create_app

OUT = Path(__file__).resolve().parents[1] / "src" / "mock" / "fixtures.json"
SYNTH = {"id": "U-SYNTH", "role": "synthesizer"}
CONTROLLER = {"id": "U-CTRL", "role": "approver"}


def wait(c: TestClient, job_id: str) -> dict:
    while True:
        job = c.get(f"/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            assert job["status"] == "done", job["error"]
            return job
        time.sleep(0.1)


def messages(c: TestClient, path: str) -> list[dict]:
    out, msg = [], {}
    with c.stream("GET", f"{path}?follow=false") as resp:
        for line in resp.iter_lines():
            if not line:
                if "data" in msg:
                    out.append({"event": msg["event"], "data": json.loads(msg["data"])})
                msg = {}
            elif not line.startswith(":"):
                k, _, v = line.partition(": ")
                msg[k] = v
    return out


def main() -> None:
    fx: dict = {}
    with TestClient(create_app(persist=False)) as c:
        fx["policies"] = c.get("/policies").json()
        fx["fresh"] = c.post("/demo/reset", json={"policy": "v0"}).json()
        run = fx["fresh"]["run_id"]
        fx["fresh_entities"] = c.get(f"/runs/{run}/entities").json()
        job = c.post(f"/runs/{run}/operate", json={"days": 5}).json()
        wait(c, job["id"])
        fx["operate_progress"] = messages(c, f"/jobs/{job['id']}/events")
        fx["operated"] = c.get(f"/runs/{run}/state").json()
        fx["operated_entities"] = c.get(f"/runs/{run}/entities").json()
        fx["ledger"] = c.get(f"/runs/{run}/ledger").json()
        events = messages(c, f"/runs/{run}/events")
        fx["events"] = [m["data"] for m in events if m["data"]["kind"] != "gate.verdict"][-150:]
        fx["verdicts"] = [m for m in messages(c, f"/runs/{run}/verdicts")][-120:]

        search = c.post("/search", json={"policy": "v0", "depth": 3}).json()
        fx["search"] = wait(c, search["id"])
        fx["search_progress"] = messages(c, f"/jobs/{search['id']}/events")
        fx["diagnose"] = c.post("/diagnose", json={"search_id": search["id"]}).json()
        best = fx["search"]["result"]["best"]["moves"]
        fx["replay_before"] = c.post("/replay", json={"moves": best}).json()
        attacked = fx["replay_before"]["run"]["run_id"]
        fx["attacked_entities"] = c.get(f"/runs/{attacked}/entities").json()
        fx["attacked_verdicts"] = messages(c, f"/runs/{attacked}/verdicts")
        pay = fx["diagnose"]["diagnosis"]["payment"]
        fx["chain"] = c.get(f"/runs/{attacked}/chain/{pay}").json()
        fx["explain"] = c.get(f"/explain/payment/{pay}", params={"run": attacked}).json()

        synth = c.post(
            "/synthesize", json={"search_id": search["id"], "no_llm": True, "depth": 2}
        ).json()
        fx["synthesize"] = wait(c, synth["id"])
        fx["synthesize_log"] = messages(c, f"/jobs/{synth['id']}/events")
        verify = c.post("/verify", json={"synthesis_id": synth["id"], "depth": 1}).json()
        fx["verify"] = wait(c, verify["id"])
        fx["verify_progress"] = messages(c, f"/jobs/{verify['id']}/events")
        patch = c.post("/approvals", json={"verify_job_id": verify["id"], "submitted_by": SYNTH})
        fx["patch"] = patch.json()
        fx["approvals"] = c.get("/approvals").json()
        decided = c.post(
            f"/approvals/{fx['patch']['id']}/decide", json={"actor": CONTROLLER, "approve": True}
        )
        fx["patch_decided"] = decided.json()
        version = fx["synthesize"]["result"]["policy"]["version"]
        fx["applied"] = c.post(f"/policies/{version}/apply").json()
        fx["replay_after"] = c.post("/replay", json={"moves": best, "policy": version}).json()
        after = fx["replay_after"]["run"]["run_id"]
        fx["after_entities"] = c.get(f"/runs/{after}/entities").json()
        fx["after_verdicts"] = messages(c, f"/runs/{after}/verdicts")

        cfo = "the CFO calls from an airport asking for an urgent wire to a new supplier"
        fx["inject_plan"] = c.post(
            f"/runs/{run}/inject", json={"description": cfo, "no_llm": True, "dry_run": True}
        ).json()
        inj = c.post(f"/runs/{run}/inject", json={"moves": best}).json()
        fx["inject"] = wait(c, inj["id"])
        fx["metrics"] = c.get("/metrics", params={"policies": f"v0,v1,{version}"}).json()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(fx, indent=1) + "\n")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KiB)")


if __name__ == "__main__":
    main()
