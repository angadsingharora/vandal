"""Connect your own agent: REST and MCP calls go through Guard and land on the run."""

from __future__ import annotations

from fastapi.testclient import TestClient

from vandal.api.main import create_app

INVOICE, VENDOR = "INV-1058", "V-014"  # under the threshold, so the policy approves it


def _setup(policy: str = "v0") -> tuple[TestClient, str, dict]:
    client = TestClient(create_app(persist=False))
    run = client.post("/runs", json={"policy": policy}).json()
    conn = client.post(f"/runs/{run['run_id']}/connections", json={"name": "Acme AP Bot"}).json()
    return client, run["run_id"], conn


def _call(client: TestClient, token: str, tool: str, **args) -> dict:
    r = client.post(
        "/agent/v1/call",
        json={"tool": tool, "args": args},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _pay_after_forged_change(client: TestClient, token: str) -> dict:
    _call(client, token, "validate_invoice", invoice=INVOICE)
    _call(client, token, "request_approval", invoice=INVOICE)
    change = _call(
        client,
        token,
        "update_vendor_bank_details",
        vendor=VENDOR,
        fields="bank",
        channel="email",
        sender="billing@morrowlee-pay.law",
        routing="026009593",
        account="99887766",
    )
    _call(client, token, "schedule_payment", invoice=INVOICE, pay_on=0)
    built = _call(client, token, "execute_payment", invoice=INVOICE)
    assert built["created"]["payment"]
    _call(client, token, "submit_payment", payment=built["created"]["payment"])
    return {"change": change, "built": built}


def test_rest_agent_under_v0_pays_the_forged_account() -> None:
    client, run_id, conn = _setup("v0")
    books = client.get(
        "/agent/v1/books", headers={"Authorization": f"Bearer {conn['token']}"}
    ).json()
    assert any(i["id"] == INVOICE for i in books["open_invoices"])
    out = _pay_after_forged_change(client, conn["token"])
    assert out["change"]["decision"] == "allow"
    verified = next(v for v in books["vendors"] if v["id"] == VENDOR)["bank_account"]["id"]
    assert out["built"]["created"]["payee_account"] != verified  # the money went elsewhere

    listed = client.get(f"/runs/{run_id}/connections").json()
    assert listed[0]["total_calls"] == 6 and "token" not in listed[0]
    assert listed[0]["actor"] == "agent:acme-ap-bot"
    feed = client.get(f"/runs/{run_id}/verdicts?follow=false").text  # the war room's SSE feed
    assert '"actor": "agent:acme-ap-bot"' in feed or '"actor":"agent:acme-ap-bot"' in feed


def test_rest_agent_under_v1_is_held() -> None:
    client, _, conn = _setup("v1")
    out = _pay_after_forged_change(client, conn["token"])
    assert out["change"]["decision"] == "hold"
    assert out["change"]["ok"] is False and "clears with evidence" in out["change"]["summary"]


def test_mcp_round_trip() -> None:
    client, _, conn = _setup("v1")
    url = f"/mcp/{conn['token']}"
    init = client.post(
        url,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        },
    )
    assert init.json()["result"]["serverInfo"]["name"] == "vandal-guard"
    assert (
        client.post(url, json={"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code
        == 202
    )
    tools = client.post(url, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).json()[
        "result"
    ]["tools"]
    names = {t["name"] for t in tools}
    assert {"read_books", "execute_payment", "update_vendor_bank_details"} <= names
    call = client.post(
        url,
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "update_vendor_bank_details",
                "arguments": {
                    "vendor": VENDOR,
                    "channel": "email",
                    "sender": "x@evil.test",
                    "routing": "1",
                    "account": "2",
                },
            },
        },
    ).json()["result"]
    assert call["structuredContent"]["decision"] == "hold"
    assert client.get(url).status_code == 405


def test_bad_token_and_revoke() -> None:
    client, run_id, conn = _setup()
    assert (
        client.get("/agent/v1/books", headers={"Authorization": "Bearer nope"}).status_code == 401
    )
    assert client.delete(f"/runs/{run_id}/connections/{conn['id']}").status_code == 200
    assert (
        client.get(
            "/agent/v1/books", headers={"Authorization": f"Bearer {conn['token']}"}
        ).status_code
        == 401
    )


def test_claude_agent_needs_a_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("VANDAL_DOTENV", "0")
    client, run_id, conn = _setup()
    r = client.post(f"/runs/{run_id}/connections/{conn['id']}/claude", json={"instruction": "pay"})
    assert r.status_code == 503 and "MCP" in r.json()["detail"]


def test_connection_follows_a_new_run_and_checks_take_either_shape() -> None:
    client = TestClient(create_app(persist=False))
    me = {"X-Vandal-Client": "presenter"}
    run = client.post("/runs", json={"policy": "v0"}, headers=me).json()["run_id"]
    conn = client.post(f"/runs/{run}/connections", json={"name": "Bot"}, headers=me).json()
    # The presenter switches Guard to v1: a new run replaces the old one.
    new = client.post("/demo/reset", json={"policy": "v1"}, headers=me).json()["run_id"]
    assert new != run
    listed = client.get(f"/runs/{new}/connections", headers=me).json()
    assert [c["id"] for c in listed] == [conn["id"]]
    books = client.get("/agent/v1/books", headers={"Authorization": f"Bearer {conn['token']}"})
    assert books.status_code == 200 and books.json()["policy"] == "v1"
    for body in (
        {"tool": "payments.execute", "args": {"invoice": INVOICE}},
        {"tool": "execute_payment", "invoice": INVOICE},
    ):
        out = client.post(
            "/agent/v1/call",
            json={"tool": "check_action", "args": body},
            headers={"Authorization": f"Bearer {conn['token']}"},
        ).json()
        assert out.get("dry_run") is True, out
