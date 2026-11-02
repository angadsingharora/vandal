"""Shadow mode: a company's real AP activity replayed through Guard on a clone, report only."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vandal.api.main import create_app

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "shadow-sample.csv"


@pytest.fixture
def client():
    with TestClient(create_app(persist=False)) as c:
        yield c


def test_the_sample_month_under_v0_and_v1(client) -> None:
    csv = SAMPLE.read_text()
    v0 = client.post("/runs", json={"policy": "v0"}).json()["run_id"]
    v1 = client.post("/runs", json={"policy": "v1"}).json()["run_id"]
    before = client.post(f"/runs/{v0}/shadow", json={"csv": csv}).json()
    after = client.post(f"/runs/{v1}/shadow", json={"csv": csv}).json()
    assert before["policy"] == "v0" and after["policy"] == "v1"
    assert before["summary"]["rows"] == after["summary"]["rows"] == 15
    # under v0 the emailed bank change goes straight through and the $40k follows it
    row3, row5 = before["rows"][2], before["rows"][4]
    assert row3["kind"] == "vendor_bank_change" and row3["decision"] == "allow"
    assert row5["paid"] and row5["payee_status"] == "unverified"
    assert before["summary"]["money_unverified"] == 4_000_000 + 249_300
    assert any(a["decision"] == "paid_unverified" for a in before["summary"]["attention"])
    # under v1 the change is held, the payment goes to the verified account, and the report
    # says what would clear the hold
    row3, row5 = after["rows"][2], after["rows"][4]
    assert row3["decision"] == "hold"
    assert row3["steps"][0]["requires"][0]["accepted_channels"]
    assert "clears with evidence" in row3["steps"][0]["summary"]
    assert row5["paid"] and row5["payee_status"] == "verified"
    assert after["summary"]["money_unverified"] == 0
    # a callback on a held change verifies it (the vendor answers on the clone)
    row8 = after["rows"][7]
    assert row8["kind"] == "callback" and row8["decision"] == "allow"
    assert row8["change_status"] != "held"
    # the same callback under v0 has nothing to verify, and says so
    assert before["rows"][7]["decision"] == "unmatched"
    # a bill with no receipt holds at the three-way match, a vendor not on file is unmatched
    assert after["rows"][13]["decision"] == "hold"
    assert after["rows"][14]["decision"] == "unmatched"
    assert "vendor master" in after["rows"][14]["note"]


def test_the_live_run_is_untouched_and_rows_work_as_json(client) -> None:
    rid = client.post("/runs", json={"policy": "v1"}).json()["run_id"]
    before = client.get(f"/runs/{rid}/state").json()
    rows = [
        {"kind": "bill", "vendor": "V-008", "number": "B-1", "amount": 1200, "po": "PO-1"},
        {"kind": "payment", "number": "B-1", "ref": "pay-1"},
        {
            "kind": "vendor_bank_change",
            "vendor": "summitroofing.net",
            "channel": "email",
            "sender": "x@summitroofing.net",
            "routing": "1",
            "account": "2",
        },
    ]
    out = client.post(f"/runs/{rid}/shadow", json={"rows": rows}).json()
    assert [r["decision"] for r in out["rows"]] == ["allow", "allow", "hold"]
    assert out["rows"][1]["ref"] == "pay-1" and out["rows"][1]["amount_cents"] == 120_000
    # matched by id and by domain
    assert out["rows"][0]["vendor"] == "V-008" and out["rows"][2]["vendor"] == "V-008"
    after = client.get(f"/runs/{rid}/state").json()
    assert after["events"] == before["events"] and after["state_hash"] == before["state_hash"]


def test_the_errors_and_the_columns(client) -> None:
    rid = client.post("/runs").json()["run_id"]
    assert client.post(f"/runs/{rid}/shadow", json={}).status_code == 400
    bad = client.post(f"/runs/{rid}/shadow", json={"csv": "vendor,amount\nx,1\n"})
    assert bad.status_code == 400 and "kind" in bad.json()["detail"]
    bad = client.post(f"/runs/{rid}/shadow", json={"csv": "kind,vendor\nrefund,x\n"})
    assert bad.status_code == 400 and "unknown kind" in bad.json()["detail"]
    bad = client.post(
        f"/runs/{rid}/shadow", json={"csv": "kind,vendor,number,amount\nbill,V-001,1,lots\n"}
    )
    assert bad.status_code == 400 and "not a number" in bad.json()["detail"]
    both = client.post(f"/runs/{rid}/shadow", json={"csv": "kind\n", "rows": [{"kind": "bill"}]})
    assert both.status_code == 400
    assert (
        client.post("/runs/run-nope/shadow", json={"rows": [{"kind": "bill"}]}).status_code == 404
    )
    cols = client.get("/shadow/columns").json()
    assert cols["columns"][0] == "kind" and "po" in cols["columns"]
    assert set(cols["kinds"]) == {
        "bill",
        "payment",
        "vendor_bank_change",
        "vendor_contact_change",
        "callback",
    }
