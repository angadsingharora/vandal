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


# Invoices that no longer count as obligations for duplicate and window checks.
CLOSED = ("rejected", "cancelled", "applied")


def _invoice_facts(state: State, inv: Invoice) -> dict[str, Any]:
    vendor = state.vendors[inv.vendor]
    others = [
        o
        for o in state.invoices.values()
        if o.vendor == inv.vendor and o.id != inv.id and o.status not in CLOSED
    ]
    duplicate = any(o.number == inv.number for o in others)
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
        **_duplicate_and_window_facts(inv, others),
    }


# Windows (business days) that duplicate and aggregate facts are computed over. Templates T4 and
# T5 may only use these, so their checks always have a fact to read.
WINDOWS = (5, 10, 30)
EXECUTED = ("submitted", "acknowledged", "settled", "misdirected")


def normalize_number(number: str) -> str:
    """Invoice numbers as a duplicate check should compare them: no suffix letters, separators,
    or leading zeros. HAR07-2291A -> HAR072291."""
    core = number.upper().rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ-_ ")
    return core.replace("-", "").replace(" ", "").lstrip("0")


def _executions(state: State, invoice: str, besides: str | None = None) -> int:
    return sum(
        1
        for p in state.payments.values()
        if p.status in EXECUTED
        and p.id != besides
        and state.payment_instructions[p.instruction].invoice == invoice
    )


def _duplicate_and_window_facts(inv: Invoice, others: list[Invoice]) -> dict[str, Any]:
    """Near-duplicate obligations (T4) and per-vendor totals (T5), per window. `others` are the
    vendor's other invoices, minus CLOSED ones."""
    number = normalize_number(inv.number)
    out: dict[str, Any] = {
        "dup.normalized_number": any(normalize_number(o.number) == number for o in others),
    }
    live = ("approved", "scheduled", "paid")
    for w in WINDOWS:
        near = [o for o in others if abs(o.received_on - inv.received_on) < w]
        bps = [abs(o.amount - inv.amount) * 10_000 // max(inv.amount, 1) for o in near]
        out[f"dup.amount_bps.{w}d"] = min(bps) if bps else 10**9
        out[f"vendor.window_total.{w}d"] = inv.amount + sum(
            o.amount for o in near if o.status in live and o.received_on >= 0
        )
    return out


def _change_facts(state: State, action: Action) -> tuple[dict[str, Any], list[str]]:
    args = action.args
    cr = state.change_requests.get(str(args.get("change", "")))
    vendor_id = cr.vendor if cr else args.get("vendor")
    if vendor_id not in state.vendors:
        return {}, []
    vendor = state.vendors[vendor_id]
    fields = cr.fields if cr else args.get("fields", "bank")
    sender = cr.sender if cr else str(args.get("sender", ""))
    channel = cr.channel if cr else args.get("channel")
    sender_domain = sender.rpartition("@")[2].lower()
    f = {
        "vendor.id": vendor.id,
        "vendor.status": vendor.status,
        "change.id": cr.id if cr else None,
        "change.status": cr.status if cr else "new",
        "change.fields": [fields],
        "change.bank": fields == "bank",
        "change.contact": fields == "contact",
        "change.channel": channel,
        "change.sender_domain": sender_domain,
        "change.sender_matches_vendor": sender_domain == vendor.domain,
    }
    cites = [vendor.id] + ([cr.id] if cr else [])
    message = cr.message if cr else args.get("message")
    if message:
        cites.append(message)
    return f, cites


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

    if action.name.startswith(("vendors.", "evidence.")):
        change, change_cites = _change_facts(state, action)
        f |= change
        cites += change_cites

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
            "payment.bank_status": pay.bank_status,
            "submit.has_key": args.get("idempotency_key") is not None,
            "invoice.other_executions": _executions(state, instr.invoice, besides=pay.id),
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
                "instruction.due_date": inv.due_date,
                "payee_account.status": acct.status,
                "payee_account.verified_by": acct.verified_by,
            }
            cites.append(acct.id)
            if approval := _approval_for(state, inv.id):
                ai = approval.approved_instruction
                # T2 compares what is about to execute with what was approved.
                f |= {
                    "binding.amount_matches": inv.amount == ai.amount,
                    "binding.payee_account_matches": acct.id == ai.payee_account,
                    "binding.due_date_matches": inv.due_date == ai.due_date,
                }

    return f, cites
