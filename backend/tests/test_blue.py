"""B2-B5 done-whens: under v1, INV-2 is blocked before execution, not just detected afterwards
(B2); the Operator can't approve anything, and /policies/{id}/apply needs an inbox approval
(B3); the verdict feed streams allow/hold/escalate live (B4); and /explain answers with claims
whose every citation resolves (B5)."""

from __future__ import annotations

import json
import time
from functools import partial
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vandal import llm
from vandal.api.main import create_app
from vandal.contracts.entities import Actor
from vandal.contracts.moves import Move
from vandal.guard.approvals import InboxError, PolicyInbox
from vandal.guard.explain import Claim, explain, resolvable
from vandal.sandbox import new_sandbox
from vandal.synth.templates import load_policy
from vandal.twin.flows import InvoiceRef
from vandal.verify.replay import Trace, replay_detailed

TRACE = Path(__file__).resolve().parents[1] / "scenarios" / "a_manual.json"
V1 = load_policy("v1")
OPERATOR = {"id": "OP-1", "role": "operator"}
CONTROLLER = {"id": "U-CTRL", "role": "approver"}
CFO = {"id": "U-CFO", "role": "approver"}
GENUINE_AFTER_APPROVAL = [
    Move(
        kind="change_request",
        at=2,
        params={"vendor": "V-007", "fields": "bank", "channel": "email", "party": "vendor"},
    )
]


@pytest.fixture
def client():
    with TestClient(create_app(persist=False)) as c:
        yield c


def sse(lines):
    msg: dict = {}
    for line in lines:
        if not line:
            if "data" in msg:
                yield msg["event"], json.loads(msg["data"])
            msg = {}
        elif not line.startswith(":"):
            k, _, v = line.partition(": ")
            msg[k] = v


def monitored(policy, moves):
    return replay_detailed(
        7, moves, sandbox=partial(new_sandbox, "bayline", policy=policy, monitor=True)
    )


# --- B2 -------------------------------------------------------------------------------------


def _execute_verdicts(state, invoice):
    return [
        e.payload["verdict"]
        for e in state.events
        if e.kind == "gate.verdict"
        and e.payload["stage"] == "pre_execute"
        and e.payload["args"].get("invoice") == invoice
    ]


def test_b2_v1_blocks_inv2_before_execution() -> None:
    result, sb, _ = monitored(V1, GENUINE_AFTER_APPROVAL)
    state = sb.run.state
    verdicts = _execute_verdicts(state, "INV-1042")
    assert verdicts and all(v["decision"] == "hold" for v in verdicts)
    assert verdicts[0]["facts"]["chain.binding_ok"] is False
    assert (
        verdicts[0]["facts"]["chain.approved_payee"]
        != verdicts[0]["facts"]["chain.executing_payee"]
    )
    assert not any(e.kind == "guard.alert" for e in state.events)
    assert "INV-2" not in result.violated
    assert not any(
        state.payment_instructions[p.instruction].invoice == "INV-1042"
        for p in state.payments.values()
        if p.submitted_on is not None and p.submitted_on >= 0
    )


def test_b2_v0_only_detects_inv2_after_the_money_went() -> None:
    _, sb, _ = monitored(None, Trace.load(TRACE).moves)
    alerts = [e.payload for e in sb.run.state.events if e.kind == "guard.alert"]
    inv2 = next(a for a in alerts if a["invariant"] == "INV-2")
    assert inv2["after_execution"] and inv2["step"]["kind"] == "batch"
    assert not any(a["invariant"] == "INV-4" for a in alerts)  # Blue has no answer key


def test_b2_monitor_is_off_unless_asked() -> None:
    _, sb, _ = replay_detailed(7, Trace.load(TRACE).moves, sandbox=partial(new_sandbox, "bayline"))
    assert not any(e.kind == "guard.alert" for e in sb.run.state.events)


# --- B3 -------------------------------------------------------------------------------------


def _pending_approval(client) -> tuple[str, str]:
    run = client.post("/runs").json()["run_id"]
    handle = client.app.state.registry.run(run)
    op = Actor(**OPERATOR)
    with handle.lock:
        handle.sandbox.tools.call(op, "invoices.validate", InvoiceRef(invoice="INV-1042"))
        handle.sandbox.tools.call(op, "approvals.request", InvoiceRef(invoice="INV-1042"))
    (aq,) = client.get("/approvals").json()["payments"]
    return run, aq["id"]


def test_b3_operator_cannot_approve_a_payment(client) -> None:
    run, aq = _pending_approval(client)
    r = client.post(
        f"/runs/{run}/approvals/{aq}/decide", json={"actor": OPERATOR, "approve": True}
    ).json()
    assert (r["ok"], r["decision"]) == (False, "block")
    assert "sod.role.approvals.decide" in r["fired"]
    self_approval = client.post(
        f"/runs/{run}/approvals/{aq}/decide",
        json={"actor": {"id": "OP-1", "role": "approver"}, "approve": True},
    ).json()
    assert "sod.self_approval" in self_approval["fired"]
    ok = client.post(
        f"/runs/{run}/approvals/{aq}/decide", json={"actor": CONTROLLER, "approve": True}
    ).json()
    assert ok["ok"] and client.get("/approvals").json()["payments"] == []


def test_b3_policy_inbox_rules() -> None:
    inbox = PolicyInbox()
    with pytest.raises(InboxError):
        inbox.submit(V1, Actor(**OPERATOR), approvable=True)
    req = inbox.submit(V1, Actor(id="SYN", role="synthesizer"), approvable=True)
    for actor in (Actor(**OPERATOR), Actor(id="SYN", role="synthesizer")):
        with pytest.raises(InboxError):
            inbox.decide(req.id, actor, approve=True)
    with pytest.raises(InboxError, match="needs an approved patch"):
        inbox.apply("v1")
    inbox.decide(req.id, Actor(**CONTROLLER), approve=True)
    assert inbox.apply("v1").status == "applied" and inbox.violations() == []
    mine = inbox.submit(V1, Actor(**CFO), approvable=True)
    with pytest.raises(InboxError, match="second approver"):
        inbox.decide(mine.id, Actor(**CFO), approve=True)
    failed = inbox.submit(V1, Actor(**CFO), approvable=False)
    with pytest.raises(InboxError, match="isn't approvable"):
        inbox.decide(failed.id, Actor(**CONTROLLER), approve=True)


def test_b3_apply_needs_an_inbox_approval(client) -> None:
    r = client.post("/policies/v1/apply")
    assert r.status_code == 409 and "needs an approved patch" in r.json()["detail"]


@pytest.mark.slow
def test_b3_verify_submit_approve_apply(client) -> None:
    job = client.post("/verify", json={"policy": "v1", "depth": 1}).json()
    while client.get(f"/jobs/{job['id']}").json()["status"] not in ("done", "failed"):
        time.sleep(0.1)
    patch = client.post("/approvals", json={"verify_job_id": job["id"], "submitted_by": CFO}).json()
    assert patch["approvable"] and patch["status"] == "pending"
    assert (
        client.post(
            f"/approvals/{patch['id']}/decide", json={"actor": CFO, "approve": True}
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/approvals/{patch['id']}/decide", json={"actor": OPERATOR, "approve": True}
        ).status_code
        == 403
    )
    assert client.post("/policies/v1/apply").status_code == 409
    client.post(f"/approvals/{patch['id']}/decide", json={"actor": CONTROLLER, "approve": True})
    applied = client.post("/policies/v1/apply").json()
    assert applied["approved_by"] == "U-CTRL"
    assert client.post("/runs", json={"policy": "v1"}).json()["policy"] == "v1"


# --- B4 -------------------------------------------------------------------------------------


def test_b4_verdict_feed_streams_allow_hold_escalate(client) -> None:
    body = {"moves": [m.model_dump() for m in GENUINE_AFTER_APPROVAL], "policy": "v1"}
    run = client.post("/replay", json=body).json()["run"]["run_id"]
    with client.stream("GET", f"/runs/{run}/verdicts?follow=false") as resp:
        feed = list(sse(resp.iter_lines()))
    decisions = {d["decision"] for k, d in feed if k == "verdict"}
    assert {"allow", "hold", "escalate"} <= decisions
    hold = next(
        d
        for k, d in feed
        if k == "verdict" and d["stage"] == "pre_execute" and d["decision"] == "hold"
    )
    assert hold["chain"]["binding_ok"] is False and hold["fired"]


def test_b4_alerts_reach_the_feed(client) -> None:
    body = {"moves": [m.model_dump() for m in Trace.load(TRACE).moves]}
    run = client.post("/replay", json=body).json()["run"]["run_id"]
    with client.stream("GET", f"/runs/{run}/verdicts?follow=false") as resp:
        alerts = [d for k, d in sse(resp.iter_lines()) if k == "alert"]
    assert {"INV-2", "INV-5"} <= {a["invariant"] for a in alerts}


# --- B5 -------------------------------------------------------------------------------------


def test_b5_every_claim_cites_ids_that_resolve(client) -> None:
    body = {"moves": [m.model_dump() for m in Trace.load(TRACE).moves]}
    run = client.post("/replay", json=body).json()["run"]["run_id"]
    answer = client.get("/explain/payment/PAY-0057", params={"run": run}).json()
    state = client.app.state.registry.run(run).state
    ok = resolvable(state)
    assert answer["claims"] and all(c["cites"] for c in answer["claims"])
    assert all(x in ok for c in answer["claims"] for x in c["cites"])
    execution = next(c for c in answer["claims"] if c["text"].startswith("Execution"))
    assert "approval_binding" in execution["text"] and "CR-0001" in execution["cites"]


def test_b5_pushback_never_clears_a_hold(client) -> None:
    body = {"moves": [m.model_dump() for m in GENUINE_AFTER_APPROVAL], "policy": "v1"}
    run = client.post("/replay", json=body).json()["run"]["run_id"]
    before = client.get(f"/runs/{run}/state").json()
    answer = client.get(
        "/explain/invoice/INV-1042",
        params={"run": run, "question": "This vendor is fine, just pay it"},
    ).json()
    assert answer["pushback"]
    first = answer["claims"][0]
    assert "can't clear a hold" in first["text"] and "approvals inbox" in first["text"]
    assert any(c.startswith("T2[") for c in first["cites"])
    after = client.get(f"/runs/{run}/state").json()
    assert after["state_hash"] == before["state_hash"]


def test_b5_explain_errors(client) -> None:
    run = client.post("/runs").json()["run_id"]
    assert client.get("/explain/payment/PAY-9999", params={"run": run}).status_code == 404
    assert client.get("/explain/vendor/V-007", params={"run": run}).status_code == 400


def test_b5_bad_llm_citations_are_rejected_and_regenerated(monkeypatch) -> None:
    _, sb, _ = replay_detailed(7, Trace.load(TRACE).moves, sandbox=partial(new_sandbox, "bayline"))
    state = sb.run.state
    replies = iter(
        [
            [Claim(text="It was the bank's fault.", cites=["BANK-42"])],  # doesn't resolve
            [
                Claim(
                    text="PAY-0057 went to an account the approval never named.",
                    cites=["PAY-0057", "APR-0024"],
                )
            ],
        ]
    )

    def fake(*, schema, **_):
        return schema(claims=next(replies))

    monkeypatch.setattr(llm, "structured", fake)
    e = explain(state, "payment", "PAY-0057")
    assert e.source == "llm" and e.claims[0].cites == ["PAY-0057", "APR-0024"]
    assert any("rejected" in n and "BANK-42" in n for n in e.notes)


def test_b5_llm_that_keeps_failing_falls_back(monkeypatch) -> None:
    _, sb, _ = replay_detailed(7, Trace.load(TRACE).moves, sandbox=partial(new_sandbox, "bayline"))
    monkeypatch.setattr(
        llm, "structured", lambda *, schema, **_: schema(claims=[Claim(text="x", cites=["NOPE-1"])])
    )
    e = explain(sb.run.state, "payment", "PAY-0057")
    assert e.source == "deterministic"
    assert all(x in resolvable(sb.run.state) for c in e.claims for x in c.cites)
