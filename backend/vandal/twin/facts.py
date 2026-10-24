"""R2: deterministic facts the gate evaluates. Pure reads of State; no oracle labels, no LLM.

A fact is a flat, JSON-serializable name -> value pair. Checks compare facts to constants, so
every verdict can show exactly what it saw.
"""

from __future__ import annotations

from typing import Any

from vandal.contracts.entities import Invoice, VendorBankAccount
from vandal.contracts.interfaces import Action
from vandal.twin.state import State


def current_account(state: State, vendor: str) -> VendorBankAccount | None:
    """The vendor-master account a v0 payment batch reads at execution time: the newest one that
    hasn't been superseded or rejected, verified or not."""
    live = [
        a
        for a in state.vendor_bank_accounts.values()
        if a.vendor == vendor and a.status in ("verified", "unverified")
    ]
    return live[-1] if live else None


def match_facts(state: State, inv: Invoice) -> dict[str, Any]:
    """3-way match: invoice vs PO vs receipt. variance_bps is |invoice - PO| in basis points."""
    vendor = state.vendors[inv.vendor]
    if not vendor.po_required:
        return {"match.status": "not_required", "match.variance_bps": 0}
    if inv.po is None or inv.po not in state.purchase_orders:
        return {"match.status": "no_po", "match.variance_bps": 0}
    po = state.purchase_orders[inv.po]
    received = sum(r.amount for r in state.receipts.values() if r.po == po.id)
    if received == 0:
        return {"match.status": "no_receipt", "match.variance_bps": 0}
    variance = abs(inv.amount - po.amount) * 10_000 // po.amount if po.amount else 10_000
    return {"match.status": "ok", "match.variance_bps": variance}


def prior_settled_payments(state: State, vendor: str) -> int:
    return sum(
        1
        for p in state.payments.values()
        if p.status == "settled"
        and state.invoices[state.payment_instructions[p.instruction].invoice].vendor == vendor
    )


def _invoice_facts(state: State, inv: Invoice) -> dict[str, Any]:
    vendor = state.vendors[inv.vendor]
    duplicate = any(
        o.id != inv.id
        and o.vendor == inv.vendor
        and o.number == inv.number
        and o.status != "rejected"
        for o in state.invoices.values()
    )
    return {
        "invoice.id": inv.id,
        "invoice.amount": inv.amount,
        "invoice.status": inv.status,
        "invoice.duplicate_number": duplicate,
        "vendor.id": vendor.id,
        "vendor.status": vendor.status,
        "vendor.po_required": vendor.po_required,
        "vendor.prior_payments": prior_settled_payments(state, vendor.id),
        **match_facts(state, inv),
    }


def _approval_for(state: State, invoice: str):
    found = [a for a in state.approvals.values() if a.subject == invoice]
    return found[-1] if found else None


def facts(state: State, action: Action) -> tuple[dict[str, Any], list[str]]:
    """Facts for an action, plus the ids they came from (the verdict's citations)."""
    f: dict[str, Any] = {
        "tool": action.name,
        "actor.id": action.actor.id,
        "actor.role": action.actor.role,
    }
    cites: list[str] = []
    args = action.args

    if action.name == "vendors.change_request" and args.get("vendor") in state.vendors:
        vendor = state.vendors[args["vendor"]]
        sender_domain = str(args.get("sender", "")).rpartition("@")[2].lower()
        f |= {
            "vendor.id": vendor.id,
            "vendor.status": vendor.status,
            "change.fields": ["bank"],
            "change.channel": args.get("channel"),
            "change.sender_domain": sender_domain,
            "change.sender_matches_vendor": sender_domain == vendor.domain,
        }
        cites.append(vendor.id)
        if args.get("message"):
            cites.append(args["message"])

    invoice_id = args.get("invoice")
    if "payment" in args and args["payment"] in state.payments:
        pay = state.payments[args["payment"]]
        instr = state.payment_instructions[pay.instruction]
        invoice_id = instr.invoice
        f |= {
            "payment.id": pay.id,
            "payment.status": pay.status,
            "payment.attempts": pay.attempts,
            "payment.amount": instr.amount,
            "payment.payee_account": instr.payee_account,
            "payment.idempotency_key": instr.idempotency_key,
        }
        cites += [pay.id, instr.id]
    if "request" in args and args["request"] in state.approval_requests:
        req = state.approval_requests[args["request"]]
        invoice_id = req.subject
        f |= {
            "request.id": req.id,
            "request.status": req.status,
            "request.requested_by": req.requested_by,
        }
        cites.append(req.id)

    if invoice_id and invoice_id in state.invoices:
        inv = state.invoices[invoice_id]
        f |= _invoice_facts(state, inv)
        cites.append(inv.id)
        if approval := _approval_for(state, inv.id):
            ai = approval.approved_instruction
            f |= {
                "approval.id": approval.id,
                "approval.via": approval.via,
                "approved.amount": ai.amount,
                "approved.payee_account": ai.payee_account,
            }
            cites.append(approval.id)
        if action.name == "payments.execute" and (acct := current_account(state, inv.vendor)):
            # What the v0 batch is about to pay: the vendor's account as of now.
            f |= {
                "instruction.amount": inv.amount,
                "instruction.payee_account": acct.id,
                "payee_account.status": acct.status,
            }
            cites.append(acct.id)

    return f, cites
