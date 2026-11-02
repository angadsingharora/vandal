"""Guard as an API: a tool call checked against a run's books without being made."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from vandal.api.main import create_app


@pytest.fixture
def client():
    with TestClient(create_app(persist=False)) as c:
        yield c


def test_the_tools_are_listed_with_their_arguments(client) -> None:
    tools = client.get("/guard/tools").json()
    by_name = {t["tool"]: t for t in tools}
    assert "payments.execute" in by_name and "vendors.change_request" in by_name
    change = by_name["vendors.change_request"]
    assert change["stage"] == "change_request"
    assert change["stage_help"]
    names = {a["name"] for a in change["args"]}
    assert {"vendor", "fields", "channel", "sender"} <= names
    assert next(a for a in change["args"] if a["name"] == "vendor")["required"] is True


def test_a_check_is_dry_and_says_what_guard_would_do(client) -> None:
    run = client.post("/runs", json={"policy": "v1"}).json()
    rid = run["run_id"]
    body = {
        "tool": "vendors.change_request",
        "args": {
            "vendor": "V-007",
            "fields": "bank",
            "channel": "email",
            "sender": "drew.silva@harborpointbui1d.com",
            "routing": "026000847",
            "account": "9680804765",
        },
    }
    out = client.post(f"/runs/{rid}/guard/check", json=body).json()
    assert out["tool"] == "vendors.change_request" and out["stage"] == "change_request"
    assert out["policy"] == "v1"
    assert out["decision"] in ("hold", "escalate", "block")
    assert out["fired"]
    assert out["summary"].startswith("Guard ")
    assert "fired" in out["summary"]
    # the hold names what would clear it, and the books did not move
    assert out["requires"], out
    assert "clears with evidence from" in out["summary"]
    assert client.get(f"/runs/{rid}/state").json()["events"] == 0
    assert client.get(f"/runs/{rid}/entities").json()["change_requests"] == []


def test_an_allowed_call_and_the_errors(client) -> None:
    rid = client.post("/runs").json()["run_id"]
    # an actor outside segregation of duties is still ruled on; a plain operator query is allowed
    out = client.post(
        f"/runs/{rid}/guard/check",
        json={"tool": "payments.query_status", "args": {"payment": "PAY-0001"}},
    ).json()
    assert out["decision"] == "allow"
    assert out["summary"] == "Guard allows payments.query_status: nothing fired."
    bad_tool = client.post(f"/runs/{rid}/guard/check", json={"tool": "money.print", "args": {}})
    assert bad_tool.status_code == 400 and "guard/tools" in bad_tool.json()["detail"]
    bad_args = client.post(
        f"/runs/{rid}/guard/check", json={"tool": "payments.execute", "args": {}}
    )
    assert bad_args.status_code == 400 and "invoice" in bad_args.json()["detail"]
    assert (
        client.post(
            "/runs/run-nope/guard/check",
            json={"tool": "payments.execute", "args": {"invoice": "INV-1"}},
        ).status_code
        == 404
    )
