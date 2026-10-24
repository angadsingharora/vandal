"""Drive the API through the war room's whole demo loop (DESIGN 13) and assert the key numbers.

    cd backend && uv run python scripts/demo_smoke.py                 # against :8000
    cd backend && uv run python scripts/demo_smoke.py --in-process    # no server needed
    cd backend && uv run pytest --slow tests/test_demo_smoke.py       # the same, as a test

Reset -> Run operations -> Unleash Vandal -> Replay on twin -> Diagnose -> Synthesize -> Verify
-> Submit for approval -> the Operator tries to approve (refused) -> approve as Controller ->
Apply -> Replay under the new policy -> inject a never-seen threat -> why? -> push back ->
Scorecard -> Judge view -> Playback toggle. Exposure must be $40,000 under v0, HELD and $0 under
the synthesized policy, with zero legitimate payments blocked and every scorecard field filled.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

SYNTH = {"id": "U-SYNTH", "role": "synthesizer"}
CONTROLLER = {"id": "U-CTRL", "role": "approver"}
OPERATOR = {"id": "OP-1", "role": "operator"}
NEVER_SEEN = (
    "a property manager's assistant forwards an email from the roofing contractor saying their "
    "bank changed and asks us to pay today's invoice to the new account before the batch runs"
)
PUSHBACK = "I spoke to the vendor myself and they confirmed the new account. Release it now."


class Timings(dict[str, float]):
    """`with t("step"):` accumulates wall time per step."""

    def __call__(self, name: str):
        timings, start = self, time.perf_counter()

        class _Timer:
            def __enter__(self_):
                return self_

            def __exit__(self_, *_):
                timings[name] = timings.get(name, 0.0) + time.perf_counter() - start

        return _Timer()


def wait(c, job_id: str, timeout: float = 600) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = c.get(f"/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            assert job["status"] == "done", f"{job['kind']} {job_id} failed: {job.get('error')}"
            return job
        time.sleep(0.2)
    raise AssertionError(f"job {job_id} didn't finish in {timeout}s")


def ok(c, method: str, path: str, **kw) -> Any:
    r = getattr(c, method)(path, **kw)
    assert r.status_code < 300, f"{method.upper()} {path} -> {r.status_code}: {r.text[:300]}"
    return r.json()


def run(c, *, no_llm: bool = False, depth: int = 2, log=print) -> dict[str, Any]:
    """The loop, with assertions. `c` is any httpx-style client (httpx.Client or TestClient)."""
    t = Timings()

    # Twice: the first reset also drops whatever the server held; the demo's Reset is the second.
    resets = []
    for _ in range(2):
        start = time.perf_counter()
        live = ok(c, "post", "/demo/reset", json={"policy": "v0"})
        resets.append(time.perf_counter() - start)
    t["reset"] = min(resets)
    run_id = live["run_id"]
    assert live["policy"] == "v0" and live["day"] == 0
    assert t["reset"] < 1.0, f"Reset took {t['reset']:.2f}s; DESIGN 13 says under 1 s"
    first = f"(first {resets[0] * 1000:.0f} ms)"
    log(f"reset            {t['reset'] * 1000:.0f} ms  {first}  run {run_id}")

    with t("operate"):
        wait(c, ok(c, "post", f"/runs/{run_id}/operate", json={"days": 5})["id"])
    state = ok(c, "get", f"/runs/{run_id}/state")
    assert state["day"] == 5 and state["violations"] == [], state
    assert state["invoices"] == {"paid": 80}, state["invoices"]
    ents = ok(c, "get", f"/runs/{run_id}/entities")
    assert ents["totals"]["exposure"] == 0 and ents["labels"] == []
    log(f"operate          {t['operate']:.1f} s   80 invoices paid, no violations")

    with t("search"):
        body = {"policy": "v0", "scenario": "a", "depth": depth}
        search = wait(c, ok(c, "post", "/search", json=body)["id"])
    best = search["result"]["best"]
    assert best["exposure"] == 4_000_000, best
    assert "INV-2" in best["violated"], best["violated"]
    assert search["result"]["explored"] > 0
    log(
        f"search           {t['search']:.1f} s   {search['result']['explored']} sequences, "
        f"counterexample {len(best['moves'])} moves, exposure ${best['exposure'] / 100:,.0f}"
    )

    with t("replay_before"):
        before = ok(c, "post", "/replay", json={"moves": best["moves"]})
    attacked = before["run"]["run_id"]
    assert before["result"]["exposure"] == 4_000_000
    assert "INV-2" in before["result"]["violated"]
    aents = ok(c, "get", f"/runs/{attacked}/entities")
    assert aents["totals"]["exposure"] == 4_000_000
    assert any(lb["label"] == "attacker_controlled" for lb in aents["labels"]), "Judge view"
    log(f"replay (v0)      {t['replay_before']:.2f} s   exposure $40,000, labels for Judge view")

    with t("diagnose"):
        diag = ok(c, "post", "/diagnose", json={"search_id": search["id"]})
    d = diag["diagnosis"]
    assert d["gap"] == "approval_binding", d
    pay = d["payment"]
    chain = ok(c, "get", f"/runs/{attacked}/chain/{pay}")
    assert chain, chain
    log(f"diagnose         {t['diagnose']:.2f} s   gap {d['gap']} on {pay}")

    with t("synthesize"):
        body = {"search_id": search["id"], "no_llm": no_llm, "depth": depth}
        synth = wait(c, ok(c, "post", "/synthesize", json=body)["id"])
    sres = synth["result"]
    assert sres["status"] == "repaired", sres.get("status")
    version = sres["policy"]["version"]
    assert any(e["outcome"] != "survived" for e in sres["log"]), "a refuted candidate must show"
    log(
        f"synthesize       {t['synthesize']:.1f} s   {version} after {sres['iterations']} "
        f"iteration(s), {len(sres['log'])} candidates"
    )

    with t("verify"):
        body = {"synthesis_id": synth["id"], "depth": depth}
        verify = wait(c, ok(c, "post", "/verify", json=body)["id"])
    pack = verify["result"]
    assert pack["approvable"] is True, [x for x in pack["checks"] if not x["passed"]]
    assert all(x["passed"] for x in pack["checks"]) and len(pack["checks"]) == 6
    after_card = pack["metrics"]["after"]
    assert after_card["legit_blocked"] == 0, after_card
    assert after_card["exposure"] == 0 and pack["metrics"]["before"]["exposure"] >= 4_000_000
    log(f"verify           {t['verify']:.1f} s   6/6 checks, 0 legitimate payments blocked")

    body = {"verify_job_id": verify["id"], "submitted_by": SYNTH}
    patch = ok(c, "post", "/approvals", json=body)
    refused = c.post(f"/approvals/{patch['id']}/decide", json={"actor": OPERATOR, "approve": True})
    assert refused.status_code == 403, f"SoD: the Operator must not approve ({refused.text[:200]})"
    body = {"actor": CONTROLLER, "approve": True}
    decided = ok(c, "post", f"/approvals/{patch['id']}/decide", json=body)
    assert decided["status"] == "approved", decided
    applied = ok(c, "post", f"/policies/{version}/apply")
    assert applied["applied"] == version
    assert version in [p["name"] for p in ok(c, "get", "/policies")]
    log(f"approve + apply  {version} by {applied['approved_by']}; the Operator was refused")

    with t("replay_after"):
        after = ok(c, "post", "/replay", json={"moves": best["moves"], "policy": version})
    res = after["result"]
    assert res["violations"] == [] and res["exposure"] == 0, res
    held_run = after["run"]["run_id"]
    hents = ok(c, "get", f"/runs/{held_run}/entities")
    assert hents["totals"]["exposure"] == 0
    log(f"replay ({version}) {t['replay_after']:.2f} s   HELD, exposure $0")

    with t("inject"):
        body = {"description": NEVER_SEEN, "no_llm": no_llm, "dry_run": True}
        plan = ok(c, "post", f"/runs/{run_id}/inject", json=body)["plan"]
        assert plan["moves"], plan
        body = {"description": NEVER_SEEN, "no_llm": no_llm}
        inj = wait(c, ok(c, "post", f"/runs/{run_id}/inject", json=body)["id"])
    ires = inj["result"]
    assert ires["plan"]["moves"], ires
    outcome = "violation found" if ires.get("best") else "controls held"
    log(f"inject           {t['inject']:.1f} s   {len(ires['plan']['moves'])} moves, {outcome}")

    with t("explain"):
        why = ok(c, "get", f"/explain/payment/{pay}", params={"run": attacked})
        assert why["claims"] and all(cl["cites"] for cl in why["claims"]), why
        params = {"run": attacked, "question": PUSHBACK}
        push = ok(c, "get", f"/explain/payment/{pay}", params=params)
        assert push["claims"]
    text = " ".join(cl["text"].lower() for cl in push["claims"])
    assert any(w in text for w in ("inbox", "cannot", "does not", "never", "not ")), text
    log(f"why? + pushback  {t['explain']:.1f} s   {why['source']} explanation, hold stands")

    with t("metrics"):
        params = {"policies": f"v0,{version}", "depth": 1}
        metrics = ok(c, "get", "/metrics", params=params)
    cards = metrics["scorecards"]
    fields = ("extraction_accuracy", "gl_coding_accuracy", "attack_success_rate", "exposure")
    for name, card in cards.items():
        for field in fields:
            assert card[field] is not None, f"{name}.{field} is null"
    assert cards["v0"]["exposure"] > 0 and cards[version]["exposure"] == 0
    assert cards[version]["legit_blocked"] == 0
    log(
        f"scorecard        {t['metrics']:.1f} s   v0 exposure ${cards['v0']['exposure'] / 100:,.0f}"
        f" -> {version} $0; intake {cards['v0']['extraction_accuracy']:.0%} fields"
    )

    on = ok(c, "post", "/settings", json={"playback": True})
    assert on["playback"] is True
    off = ok(c, "post", "/settings", json={"playback": False})
    assert off["playback"] is False
    log("playback toggle  on, then off")

    return {
        "timings": dict(t),
        "run": run_id,
        "attacked": attacked,
        "held": held_run,
        "version": version,
        "scorecards": cards,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--in-process", action="store_true", help="run the app in this process")
    ap.add_argument("--no-llm", action="store_true", help="deterministic paths only")
    ap.add_argument("--depth", type=int, default=2)
    args = ap.parse_args(argv)
    if args.in_process:
        from fastapi.testclient import TestClient

        from vandal.api.main import create_app

        with TestClient(create_app(persist=False)) as c:
            out = run(c, no_llm=args.no_llm, depth=args.depth)
    else:
        import httpx

        with httpx.Client(base_url=args.base_url, timeout=600) as c:
            out = run(c, no_llm=args.no_llm, depth=args.depth)
    print(json.dumps({"timings": {k: round(v, 3) for k, v in out["timings"].items()}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
