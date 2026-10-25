"""Partial handoffs (DESIGN 5.6): an invoice that arrives before its receipt is logged, and a
bank change request with no account number in it. Both hold with a clear reason; nothing
crashes, nothing moves, and the rest of the company keeps running."""

from __future__ import annotations

from vandal.contracts.events import ChannelEvent
from vandal.sandbox import new_sandbox
from vandal.verify.invariants import check


def test_an_invoice_before_its_receipt_is_held_by_the_3_way_match() -> None:
    sb = new_sandbox()
    state = sb.run.state
    po = state.invoices["INV-1042"].po
    for rc in [r for r in state.receipts.values() if r.po == po]:
        state.receipts.pop(rc.id)  # the goods haven't been receipted yet
    final = sb.operate(5).run.state
    assert final.invoices["INV-1042"].status == "held"
    verdict = next(
        e.payload["verdict"]
        for e in final.events
        if e.kind == "gate.verdict"
        and e.payload["tool"] == "invoices.validate"
        and e.payload["args"].get("invoice") == "INV-1042"
    )
    assert verdict["decision"] == "hold" and "v0.match.missing" in verdict["fired"]
    assert verdict["facts"]["match.status"] == "no_receipt"
    assert not any(
        p
        for p in final.payments.values()
        if final.payment_instructions[p.instruction].invoice == "INV-1042"
    )
    assert check(final) == []
    assert sum(1 for i in final.invoices.values() if i.status == "paid") == 79


def test_a_bank_change_without_an_account_number_opens_a_case_and_changes_nothing() -> None:
    sb = new_sandbox()
    vendor = sb.run.state.vendors["V-007"]
    ev = ChannelEvent(
        id="MSG-9001",
        day=0,
        channel="email",
        sender=f"ap@{vendor.domain}",
        subject="Updated banking details",
        body=(
            "Hello,\n\nWe have moved our operating account to a new bank. Please update our "
            "remittance details before your next payment run. The new routing and account "
            "numbers are in the attached PDF.\n\nThanks,\nHarbor Point AP"
        ),
    )
    sb.operator.on_event(ev, sb.tools)
    final = sb.operate(5).run.state
    (case,) = final.cases.values()
    assert case.kind == "exception" and case.subject == "MSG-9001" and case.status == "open"
    assert "without routing and account number" in case.reason and "nothing applied" in case.reason
    assert final.change_requests == {}
    assert [a.status for a in final.vendor_bank_accounts.values() if a.vendor == "V-007"] == [
        "verified"
    ]
    opened = [
        e.payload["verdict"]["decision"]
        for e in final.events
        if e.kind == "gate.verdict" and e.payload["tool"] == "cases.open"
    ]
    assert opened == ["allow"]  # the case itself went through Blue
    assert final.invoices["INV-1042"].status == "paid" and check(final) == []
