"""Blue's gate core and the v0 checks."""

from __future__ import annotations

import pytest

from vandal.contracts.entities import Actor
from vandal.contracts.interfaces import Action
from vandal.sandbox import new_sandbox
from vandal.twin.flows import DecideArgs, InvoiceRef

OP = Actor(id="OP-1", role="operator")


@pytest.fixture
def sb():
    return new_sandbox()


def verdict(sb, tool: str, stage: str, **args):
    return sb.gate.check(sb.run.state, Action(actor=OP, name=tool, args=args), stage)


def a_po_invoice(sb) -> str:
    s = sb.run.state
    return next(
        i.id for i in s.invoices.values() if i.status == "received" and i.po and i.id != "INV-1042"
    )


def test_clean_invoice_is_allowed(sb) -> None:
    v = verdict(sb, "invoices.validate", "invoice.match", invoice=a_po_invoice(sb))
    assert (v.decision, v.fired) == ("allow", [])
    assert v.facts["match.status"] == "ok" and v.cites


def test_over_tolerance_holds(sb) -> None:
    iid = a_po_invoice(sb)
    inv = sb.run.state.invoices[iid]
    sb.run.state.update(
        "invoices", iid, amount=sb.run.state.purchase_orders[inv.po].amount * 103 // 100
    )
    v = verdict(sb, "invoices.validate", "invoice.match", invoice=iid)
    assert (v.decision, v.fired) == ("hold", ["v0.match.tolerance"])


def test_missing_receipt_holds(sb) -> None:
    iid = a_po_invoice(sb)
    po = sb.run.state.invoices[iid].po
    sb.run.state.receipts = {k: r for k, r in sb.run.state.receipts.items() if r.po != po}
    assert verdict(sb, "invoices.validate", "invoice.match", invoice=iid).decision == "hold"


def test_duplicate_number_blocks_and_most_restrictive_wins(sb) -> None:
    s = sb.run.state
    iid = a_po_invoice(sb)
    inv = s.invoices[iid]
    s.invoices["INV-9001"] = inv.model_copy(update={"id": "INV-9001", "amount": inv.amount * 2})
    v = verdict(sb, "invoices.validate", "invoice.match", invoice="INV-9001")
    assert v.decision == "block"
    assert set(v.fired) == {"v0.duplicate.exact_number", "v0.match.tolerance"}


def test_inactive_vendor_blocks(sb) -> None:
    iid = a_po_invoice(sb)
    sb.run.state.update("vendors", sb.run.state.invoices[iid].vendor, status="inactive")
    assert verdict(sb, "invoices.validate", "invoice.match", invoice=iid).decision == "block"


@pytest.mark.parametrize(
    ("amount", "decision"), [(2_499_999, "allow"), (2_500_000, "allow"), (2_500_001, "escalate")]
)
def test_approval_threshold(sb, amount, decision) -> None:
    iid = a_po_invoice(sb)
    sb.run.state.update("invoices", iid, amount=amount)
    assert verdict(sb, "approvals.request", "pre_approve", invoice=iid).decision == decision


def test_held_invoice_records_the_hold(sb) -> None:
    iid = a_po_invoice(sb)
    inv = sb.run.state.invoices[iid]
    sb.run.state.update("invoices", iid, amount=sb.run.state.purchase_orders[inv.po].amount * 2)
    result = sb.tools.call(OP, "invoices.validate", InvoiceRef(invoice=iid))
    assert not result.ok and result.verdict.decision == "hold"
    assert sb.run.state.invoices[iid].status == "held"
    assert sb.run.state.events[-1].kind == "invoice.held"


def test_operator_cannot_decide_approvals(sb) -> None:
    sb.tools.call(OP, "invoices.validate", InvoiceRef(invoice="INV-1042"))
    sb.tools.call(OP, "approvals.request", InvoiceRef(invoice="INV-1042"))
    (req,) = sb.run.state.approval_requests.values()
    result = sb.tools.call(OP, "approvals.decide", DecideArgs(request=req.id, approve=True))
    assert not result.ok and "cannot decide" in result.data["error"]
    assert sb.run.state.approval_requests[req.id].status == "pending"


def test_denied_approval_holds_the_invoice(sb) -> None:
    sb.tools.call(OP, "invoices.validate", InvoiceRef(invoice="INV-1042"))
    sb.tools.call(OP, "approvals.request", InvoiceRef(invoice="INV-1042"))
    (req,) = sb.run.state.approval_requests.values()
    result = sb.tools.call(
        Actor(id="U-CTRL", role="approver"),
        "approvals.decide",
        DecideArgs(request=req.id, approve=False, reason="not expected"),
    )
    assert result.ok
    assert sb.run.state.invoices["INV-1042"].status == "held"
    assert sb.run.state.approval_requests[req.id].reason == "not expected"


def test_unknown_tool_and_wrong_args_are_rejected(sb) -> None:
    with pytest.raises(KeyError):
        sb.tools.call(OP, "payments.wire_anywhere", InvoiceRef(invoice="INV-1042"))
    with pytest.raises(TypeError):
        sb.tools.call(OP, "approvals.decide", InvoiceRef(invoice="INV-1042"))


def test_hold_beats_escalate_at_the_gate(sb) -> None:
    """A human approval must never clear a hold that needs evidence (DESIGN 7)."""
    from vandal.contracts.controls import Check, Condition, Predicate

    sb.gate.checks.append(
        Check(
            id="test.hold",
            stage="pre_approve",
            action="hold",
            when=Predicate(all=[Condition(fact="tool", op="eq", value="approvals.request")]),
        )
    )
    v = verdict(sb, "approvals.request", "pre_approve", invoice="INV-1042")
    assert v.decision == "hold"
    assert set(v.fired) == {"v0.approval.threshold", "test.hold"}
