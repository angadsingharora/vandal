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
    bad = client.post(f"/runs/{rid}/shadow", json={"csv": "date,notes\n2026-01-01,x\n"})
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


QUICKBOOKS = """Date,Transaction Type,Num,Vendor Name,Memo,Amount,PO Number
2026-03-02,Bill,HPC-3104,Harbor Point Construction,March draw,"$18,450.00",PO-7731
2026-03-05,Bill Payment (Check),HPC-3104,Harbor Point Construction,,"18,450.00",
2026-03-09,Vendor Update,,Harbor Point Construction,,,
"""


def test_a_quickbooks_export_is_read_through_the_aliases(client) -> None:
    m = client.post("/shadow/mapping", json={"csv": QUICKBOOKS}).json()
    assert {c["source"]: c["read_as"] for c in m["columns"]} == {
        "Transaction Type": "kind",
        "Num": "number",
        "Vendor Name": "vendor",
        "Amount": "amount",
        "PO Number": "po",
    }
    assert m["ignored"] == ["Date", "Memo"] and m["problem"] is None
    assert m["rows"] == 3 and m["kinds"] == {"bill": 1, "payment": 1, "vendor_bank_change": 1}
    rid = client.post("/runs", json={"policy": "v1"}).json()["run_id"]
    out = client.post(f"/runs/{rid}/shadow", json={"csv": QUICKBOOKS}).json()
    assert [r["decision"] for r in out["rows"]] == ["allow", "allow", "hold"]
    assert out["rows"][1]["amount_cents"] == 1_845_000


def test_kind_is_inferred_from_the_columns_a_row_fills(client) -> None:
    csv = (
        "Vendor,Invoice #,Total,Routing Number,Account Number,Verified By\n"
        "Summit Roofing,SR-9,100,,,\n"
        ",SR-9,,,,\n"
        "Summit Roofing,,,1,2,\n"
        "Summit Roofing,,,,,phone_outbound\n"
    )
    m = client.post("/shadow/mapping", json={"csv": csv}).json()
    assert m["kinds"] == {"bill": 1, "payment": 1, "vendor_bank_change": 1, "callback": 1}
    m = client.post("/shadow/mapping", json={"csv": "Vendor,Notes\nSummit Roofing,x\n"}).json()
    assert m["rows"] == 0 and "can't tell" in m["problem"]


def test_compare_runs_the_month_under_both_policies(client) -> None:
    csv = SAMPLE.read_text()
    rid = client.post("/runs", json={"policy": "v0"}).json()["run_id"]
    out = client.post(f"/runs/{rid}/shadow", json={"csv": csv, "compare": "v1"}).json()
    assert out["policy"] == "v0" and out["compare"]["policy"] == "v1"
    assert out["summary"]["money_unverified"] == 4_249_300
    assert out["compare"]["summary"]["money_unverified"] == 0
    d = out["delta"]
    assert d["before"] == "v0" and d["after"] == "v1"
    assert d["money_unverified"] == -4_249_300 and d["held_or_blocked"] > 0
    assert any(m["n"] == 3 and m["before"] == "allow" and m["after"] == "hold" for m in d["moved"])
    # the report is kept as a job, so it has an address
    job = client.get(f"/jobs/{out['job_id']}").json()
    assert job["kind"] == "shadow" and job["status"] == "done"
    assert job["result"]["delta"]["money_unverified"] == -4_249_300
    assert job["meta"]["compare"] == "v1" and job["meta"]["rows"] == 15
    # comparing a policy with itself, or one that doesn't exist
    same = client.post(f"/runs/{rid}/shadow", json={"csv": csv, "compare": "v0"}).json()
    assert same["compare"] is None and same["delta"] is None
    assert client.post(f"/runs/{rid}/shadow", json={"csv": csv, "compare": "v9"}).status_code == 400


REAL = """Vendor Name,Invoice #,Amount,Transaction Type,channel,sender,routing,account
Acme Janitorial,INV-88,1250.00,Bill,,,,
Acme Janitorial,INV-88,,Bill Payment,,,,
Acme Janitorial,,,vendor_bank_change,email,billing@acme-janitorial-pay.com,026009593,99887766
Acme Janitorial,INV-91,4100.00,Bill,,,,
Acme Janitorial,INV-91,,Bill Payment,,,,
"""


def test_an_export_with_the_companys_own_vendors(client) -> None:
    rid = client.post("/runs", json={"policy": "v0"}).json()["run_id"]
    # as is, nothing in the file is on the books
    plain = client.post(f"/runs/{rid}/shadow", json={"csv": REAL}).json()
    assert plain["summary"]["by_decision"]["unmatched"] == 5 and plain["enrolled"] == []
    # enrolled, the vendor is on file and its rows run: the emailed change goes through under
    # v0 and the next payment follows it; under v1 the change is held and the money stays put
    out = client.post(
        f"/runs/{rid}/shadow", json={"csv": REAL, "enroll": True, "compare": "v1"}
    ).json()
    assert out["enrolled"] == ["Acme Janitorial"]
    assert out["summary"]["by_decision"]["unmatched"] == 0
    assert out["rows"][1]["paid"] and out["rows"][1]["payee_status"] == "verified"
    assert out["rows"][4]["paid"] and out["rows"][4]["payee_status"] == "unverified"
    assert out["summary"]["money_unverified"] == 410_000
    assert out["compare"]["rows"][2]["decision"] == "hold"
    assert out["compare"]["summary"]["money_unverified"] == 0
    assert all(r["enrolled"] for r in out["rows"])


PAID_TO = """Vendor Name,Invoice #,Amount,Transaction Type,Account Number
Acme Janitorial,INV-88,1250.00,Bill,
Acme Janitorial,INV-88,,Bill Payment,****4410
Acme Janitorial,INV-91,4100.00,Bill,
Acme Janitorial,INV-91,,Bill Payment,****7766
Acme Janitorial,INV-95,900.00,Bill,
Acme Janitorial,INV-95,,Bill Payment,****7766
Delta Elevator Co,D-204,9400.00,Bill,
Delta Elevator Co,D-204,,Bill Payment,****0031
"""


def test_a_vendor_paid_at_a_new_account_is_read_as_a_bank_change(client) -> None:
    rid = client.post("/runs", json={"policy": "v0"}).json()["run_id"]
    out = client.post(
        f"/runs/{rid}/shadow", json={"csv": PAID_TO, "enroll": True, "compare": "v1"}
    ).json()
    rows, twin = out["rows"], out["compare"]["rows"]
    # the first account a vendor is paid at is the one on file: nothing to say
    assert "inferred_change" not in rows[1] and "inferred_change" not in rows[7]
    assert rows[1]["payee_status"] == "verified"
    # the second payment went somewhere new: a change nobody verified, and the money followed
    assert rows[3]["inferred_change"] == {"account": "7766", "was": "4410"}
    assert rows[3]["steps"][0]["tool"] == "vendors.change_request"
    assert rows[3]["paid"] and rows[3]["payee_status"] == "unverified"
    # the same account again is not a second change, but it is still unverified money
    assert "inferred_change" not in rows[5] and rows[5]["payee_status"] == "unverified"
    assert out["inferred_changes"] == 1
    assert out["summary"]["money_unverified"] == 410_000 + 90_000
    # with the rule, the change is held and both payments go to the account on file
    assert twin[3]["decision"] == "hold" and twin[3]["payee_status"] == "verified"
    assert out["compare"]["summary"]["money_unverified"] == 0


def test_an_account_on_a_row_with_a_bill_number_is_not_a_change_request(client) -> None:
    csv = "Invoice #,Account Number\nINV-88,****4410\n"
    kinds = client.post("/shadow/mapping", json={"csv": csv}).json()["kinds"]
    assert kinds == {"payment": 1}
