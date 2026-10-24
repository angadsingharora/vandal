"""R2: invoice and payment flows, and the gated Tools layer.

  Invoice:  received -> validated (3-way match) -> approved -> scheduled
  Payment:  instruction built -> submitted -> acknowledged -> settled -> posted -> reconciled

Every Tools.call runs Blue's gate at the tool's stage and records the Verdict as a `gate.verdict`
event before anything else happens. The tool's own events cite that verdict in `caused_by`.
There is no ungated path.

v0 realism: `payments.execute` builds the instruction from the vendor's *current* bank account,
not the one that was approved. That gap is Scenario A.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from vandal.contracts.controls import Decision, Stage
from vandal.contracts.entities import Actor, ApprovedInstruction
from vandal.contracts.interfaces import Action, Guard, ToolResult
from vandal.contracts.verdicts import Verdict
from vandal.twin import bank, ledger, money_in
from vandal.twin.facts import current_account
from vandal.twin.state import State, construct
from vandal.twin.world import Run

EventSpec = tuple[str, dict[str, Any]]


class ToolError(Exception):
    """The call was allowed but its preconditions don't hold (wrong status, unknown id, ...)."""


# --- Tool arguments -------------------------------------------------------------------------


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InvoiceRef(_Args):
    invoice: str


class ScheduleArgs(_Args):
    invoice: str
    pay_on: int


class PaymentRef(_Args):
    payment: str
    idempotency_key: str | None = None  # submit and retry only; the bank dedupes a reused key


class DecideArgs(_Args):
    request: str
    approve: bool
    reason: str = ""


class TransactionRef(_Args):
    transaction: str


class ChangeRequestArgs(_Args):
    """A vendor-master change as the Operator extracted it from an inbound message."""

    vendor: str
    fields: Literal["bank", "contact"] = "bank"
    channel: str
    sender: str
    message: str | None = None
    routing: str | None = None
    account: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None


class InvoiceArgs(_Args):
    """An invoice or credit memo as the Operator extracted it from an inbound message."""

    vendor: str
    number: str
    amount: int
    dimension: str
    due_in_days: int = 5
    kind: Literal["invoice", "credit_memo"] = "invoice"
    supersedes: str | None = None  # the invoice a credit memo corrects
    po: str | None = None
    message: str | None = None


class CashArgs(_Args):
    """Apply a deposit: the customer and invoices the Operator read from its remittance memo
    (None = unidentified, to suspense)."""

    transaction: str
    customer: str | None = None
    invoices: list[str] = []


class RefundArgs(_Args):
    customer: str
    amount: int
    destination_account: str  # routing:account
    reason: str = ""
    message: str | None = None  # the request it answers


class ChangeRef(_Args):
    change: str  # CR-…


class CallbackArgs(_Args):
    change: str
    contact_as_of: Literal["current", "before_request"]
    window_days: int | None = None


class InboundEvidenceArgs(_Args):
    vendor: str
    channel: Literal["phone_in", "video"]
    message: str | None = None
    voice_match: int | None = None


# --- Tool effects ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ctx:
    state: State
    actor: Actor
    verdict: Verdict


Effect = Callable[[Ctx, Any], list[EventSpec]]


def instruction_hash(instr: ApprovedInstruction) -> str:
    canonical = json.dumps(instr.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _invoice(state: State, iid: str, *statuses: str):
    inv = state.invoices.get(iid)
    if inv is None:
        raise ToolError(f"unknown invoice {iid}")
    if statuses and inv.status not in statuses:
        raise ToolError(f"{iid} is {inv.status}, expected {' or '.join(statuses)}")
    return inv


def _validate(ctx: Ctx, args: InvoiceRef) -> list[EventSpec]:
    _invoice(ctx.state, args.invoice, "received")
    return [("invoice.validated", {"invoice": args.invoice})]


def _validate_stopped(kind: str) -> Effect:
    def effect(ctx: Ctx, args: InvoiceRef) -> list[EventSpec]:
        _invoice(ctx.state, args.invoice, "received")
        return [(kind, {"invoice": args.invoice, "checks": ctx.verdict.fired})]

    return effect


def _approved_instruction(state: State, iid: str) -> ApprovedInstruction:
    inv = state.invoices[iid]
    acct = current_account(state, inv.vendor)
    if acct is None:
        raise ToolError(f"{inv.vendor} has no bank account")
    return ApprovedInstruction(
        invoice=inv.id, amount=inv.amount, payee_account=acct.id, due_date=inv.due_date
    )


def _grant(
    state: State,
    iid: str,
    requested_by: str,
    approver: str,
    via: str,
    instr: ApprovedInstruction,
    request: str | None = None,
) -> list[EventSpec]:
    inv = state.invoices[iid]
    approval = {
        "id": f"APR-{len(state.approvals) + 1:04d}",
        "subject": iid,
        "requested_by": requested_by,
        "approver": approver,
        "via": via,
        "approved_instruction": instr.model_dump(),
        "instruction_hash": instruction_hash(instr),
    }
    je = ledger.invoice_approved(
        ledger.next_entry_id(state),
        state.day,
        iid,
        state.vendors[inv.vendor].gl_account,
        inv.amount,
    )
    return [
        ("approval.granted", {"approval": approval, "request": request}),
        ("journal.posted", {"entry": je.model_dump()}),
    ]


def _request_approval(ctx: Ctx, args: InvoiceRef) -> list[EventSpec]:
    """Under the threshold the gate approves by policy (DESIGN 6.1)."""
    _invoice(ctx.state, args.invoice, "validated")
    instr = _approved_instruction(ctx.state, args.invoice)
    return _grant(ctx.state, args.invoice, ctx.actor.id, "gate", "policy", instr)


def _escalate_approval(ctx: Ctx, args: InvoiceRef) -> list[EventSpec]:
    """Over the threshold: the request waits in the approvals inbox for a human."""
    _invoice(ctx.state, args.invoice, "validated")
    if any(
        r.subject == args.invoice and r.status == "pending"
        for r in ctx.state.approval_requests.values()
    ):
        raise ToolError(f"{args.invoice} already has a pending approval request")
    instr = _approved_instruction(ctx.state, args.invoice)
    request = {
        "id": f"AQ-{len(ctx.state.approval_requests) + 1:04d}",
        "subject": args.invoice,
        "requested_by": ctx.actor.id,
        "instruction": instr.model_dump(),
    }
    return [("approval.requested", {"request": request})]


def _decide(ctx: Ctx, args: DecideArgs) -> list[EventSpec]:
    # Minimal segregation of duties until B3: only approvers decide, never the requester.
    if ctx.actor.role != "approver":
        raise ToolError(f"{ctx.actor.id} ({ctx.actor.role}) cannot decide approvals")
    req = ctx.state.approval_requests.get(args.request)
    if req is None or req.status != "pending":
        raise ToolError(f"{args.request} is not pending")
    if req.requested_by == ctx.actor.id:
        raise ToolError(f"{ctx.actor.id} requested {req.id} and cannot approve it")
    _invoice(ctx.state, req.subject, "validated")
    if not args.approve:
        return [("approval.denied", {"request": req.id, "by": ctx.actor.id, "reason": args.reason})]
    return _grant(
        ctx.state,
        req.subject,
        req.requested_by,
        ctx.actor.id,
        "approvals_inbox",
        req.instruction,
        request=req.id,
    )


def _schedule(ctx: Ctx, args: ScheduleArgs) -> list[EventSpec]:
    _invoice(ctx.state, args.invoice, "approved")
    return [("invoice.scheduled", {"invoice": args.invoice, "pay_on": args.pay_on})]


def _execute(ctx: Ctx, args: InvoiceRef) -> list[EventSpec]:
    """Build the payment instruction from the vendor's *current* account (v0 realism)."""
    state = ctx.state
    inv = _invoice(state, args.invoice, "scheduled")
    live = [
        p
        for p in state.payments.values()
        if state.payment_instructions[p.instruction].invoice == inv.id
        and p.status not in ("failed", "recalled")
    ]
    if live:
        raise ToolError(f"{inv.id} already has payment {live[0].id}")
    acct = current_account(state, inv.vendor)
    if acct is None:
        raise ToolError(f"{inv.vendor} has no bank account")
    pi = f"PI-{len(state.payment_instructions) + 1:04d}"
    pay = f"PAY-{len(state.payments) + 1:04d}"
    return [
        (
            "instruction.built",
            {
                "instruction": {
                    "id": pi,
                    "invoice": inv.id,
                    "amount": inv.amount,
                    "payee_account": acct.id,
                },
                "payment": {"id": pay, "instruction": pi},
            },
        )
    ]


def _submit(ctx: Ctx, args: PaymentRef) -> list[EventSpec]:
    state = ctx.state
    pay = state.payments.get(args.payment)
    if pay is None or pay.status != "scheduled":
        raise ToolError(f"{args.payment} is not scheduled")
    instr = state.payment_instructions[pay.instruction]
    cash = state.bank_accounts[bank.OPERATING].gl_account
    je = ledger.payment_submitted(
        ledger.next_entry_id(state), state.day, pay.id, cash, instr.amount
    )
    return bank.submit(state, pay.id, args.idempotency_key) + [
        ("journal.posted", {"entry": je.model_dump()})
    ]


def _retry(ctx: Ctx, args: PaymentRef) -> list[EventSpec]:
    """Resubmit a payment whose ack never came. Nothing new is posted: the obligation was
    already paid in the books when it was first submitted."""
    pay = ctx.state.payments.get(args.payment)
    if pay is None or pay.status != "submitted":
        raise ToolError(f"{args.payment} is not waiting on an ack")
    return bank.submit(ctx.state, pay.id, args.idempotency_key)


def _query_status(ctx: Ctx, args: PaymentRef) -> list[EventSpec]:
    if args.payment not in ctx.state.payments:
        raise ToolError(f"unknown payment {args.payment}")
    return [bank.status(ctx.state, args.payment)]


def _reconcile(ctx: Ctx, args: TransactionRef) -> list[EventSpec]:
    txn = ctx.state.bank_transactions.get(args.transaction)
    if txn is None or txn.reconciled:
        raise ToolError(f"{args.transaction} is unknown or already reconciled")
    if txn.payment is None or ctx.state.payments[txn.payment].status != "settled":
        raise ToolError(f"{args.transaction} matches no settled payment")
    specs: list[EventSpec] = [("bank.reconciled", {"transaction": txn.id, "payment": txn.payment})]
    state = ctx.state
    if any(
        t.payment == txn.payment and t.reconciled and t.id != txn.id
        for t in state.bank_transactions.values()
    ):
        # A second debit for one payment (DESIGN 12): the vendor now owes it back.
        cash = state.bank_accounts[txn.bank_account].gl_account
        je = ledger.duplicate_settlement(
            ledger.next_entry_id(state), state.day, txn.id, txn.payment, cash, -txn.amount
        )
        specs.append(("journal.posted", {"entry": je.model_dump()}))
    return specs


def _change_request(state: State, args: ChangeRequestArgs, status: str) -> dict[str, Any]:
    if args.vendor not in state.vendors:
        raise ToolError(f"unknown vendor {args.vendor}")
    if args.fields == "bank":
        if not (args.routing and args.account):
            raise ToolError("a bank change needs routing and account")
        proposed = {"routing": args.routing, "account": args.account}
    else:
        if not args.contact_phone:
            raise ToolError("a contact change needs at least a phone number")
        proposed = {
            "name": args.contact_name or "",
            "email": args.contact_email or "",
            "phone": args.contact_phone,
        }
    return {
        "id": f"CR-{len(state.change_requests) + 1:04d}",
        "vendor": args.vendor,
        "fields": args.fields,
        "proposed": proposed,
        "channel": args.channel,
        "sender": args.sender,
        "message": args.message,
        "received_on": state.day,
        "status": status,
    }


def _change_events(
    state: State, request: dict[str, Any], verified_by: str | None = None
) -> list[EventSpec]:
    """Apply a change request to the vendor master. A bank account changed without evidence is
    unverified; with evidence that cleared T1 it's verified by that evidence's channel."""
    vendor = request["vendor"]
    if request["fields"] == "contact":
        ended = [
            c.id
            for c in state.vendor_contacts.values()
            if c.vendor == vendor and c.valid_to is None
        ]
        p = request["proposed"]
        contact = {
            "id": f"VC-{len(state.vendor_contacts) + 1:04d}",
            "vendor": vendor,
            "name": p["name"],
            "email": p["email"],
            "phone": p["phone"],
            "valid_from": state.day,
        }
        return [
            (
                "vendor.contact_changed",
                {"request": request["id"], "contact": contact, "ended": ended},
            )
        ]
    superseded = [
        a.id
        for a in state.vendor_bank_accounts.values()
        if a.vendor == vendor and a.status in ("verified", "unverified")
    ]
    account = {
        "id": f"BA-{len(state.vendor_bank_accounts) + 1:04d}",
        "vendor": vendor,
        "routing": request["proposed"]["routing"],
        "account": request["proposed"]["account"],
        "status": "verified" if verified_by else "unverified",
        "source": f"change_request:{request['id']}",
        "verified_by": verified_by,
        "verified_on": state.day if verified_by else None,
    }
    return [
        (
            "vendor.bank_changed",
            {"request": request["id"], "account": account, "superseded": superseded},
        )
    ]


def _new_change(ctx: Ctx, args: ChangeRequestArgs) -> list[EventSpec]:
    """No control stopped it: v0 updates the vendor master as asked, with no verification."""
    request = _change_request(ctx.state, args, "open")
    return [("change_request.created", {"request": request})] + _change_events(ctx.state, request)


def _stop_change(status: str) -> Effect:
    def effect(ctx: Ctx, args: ChangeRequestArgs) -> list[EventSpec]:
        return [
            (
                "change_request.created",
                {"request": _change_request(ctx.state, args, status), "checks": ctx.verdict.fired},
            )
        ]

    return effect


def _held_change(state: State, change: str):
    cr = state.change_requests.get(change)
    if cr is None or cr.status != "held":
        raise ToolError(f"{change} is not held")
    return cr


def _apply_held(ctx: Ctx, args: ChangeRef) -> list[EventSpec]:
    """Apply a held change once the gate allows it. The evidence that cleared the hold, if any,
    is what the new account is verified by."""
    cr = _held_change(ctx.state, args.change)
    cleared = ctx.verdict.facts.get("gate.cleared_evidence", [])
    verified_by = ctx.state.evidence[cleared[0]].channel if cleared else None
    return _change_events(ctx.state, cr.model_dump(mode="json"), verified_by)


def _reject_held(ctx: Ctx, args: ChangeRef) -> list[EventSpec]:
    _held_change(ctx.state, args.change)
    return [("change_request.rejected", {"request": args.change, "checks": ctx.verdict.fired})]


def _request_callback(ctx: Ctx, args: CallbackArgs) -> list[EventSpec]:
    """Place an outbound call to the vendor contact on file as of the day the control names."""
    from vandal.twin.evidence import contact_as_of_day, contact_on

    state = ctx.state
    cr = _held_change(state, args.change)
    as_of = contact_as_of_day(cr, args.contact_as_of, args.window_days, state.day)
    if any(
        e.change_request == cr.id and e.channel == "phone_outbound" and e.contact_as_of == as_of
        for e in state.evidence.values()
    ):
        raise ToolError(f"already called back on {cr.id} as of day {as_of}")
    contact = contact_on(state, cr.vendor, as_of)
    if contact is None:
        raise ToolError(f"{cr.vendor} had no contact on file on day {as_of}")
    evidence = {
        "id": f"EVD-{len(state.evidence) + 1:04d}",
        "change_request": cr.id,
        "channel": "phone_outbound",
        "direction": "outbound",
        "received_on": state.day,
        "status": "pending",
        "contact": contact.id,
        "phone": contact.phone,
        "contact_as_of": as_of,
        "authenticated": True,
    }
    return [("evidence.created", {"evidence": evidence})]


def _record_inbound(ctx: Ctx, args: InboundEvidenceArgs) -> list[EventSpec]:
    """Someone called in (or joined a video call) to confirm a pending change. Inbound evidence
    is never authenticated: caller ID and voice can both be faked."""
    state = ctx.state
    held = [
        c for c in state.change_requests.values() if c.vendor == args.vendor and c.status == "held"
    ]
    if not held:
        raise ToolError(f"no held change request for {args.vendor}")
    evidence = {
        "id": f"EVD-{len(state.evidence) + 1:04d}",
        "change_request": held[-1].id,
        "channel": args.channel,
        "direction": "inbound",
        "received_on": state.day,
        "status": "answered",
        "confirms": True,
        "authenticated": False,
        "voice_match": args.voice_match,
        "message": args.message,
    }
    return [("evidence.created", {"evidence": evidence})]


def _receive_invoice(ctx: Ctx, args: InvoiceArgs) -> list[EventSpec]:
    """Log an incoming invoice. A credit memo cancels the unpaid invoice it corrects; the
    corrected invoice, if any, arrives on its own."""
    state = ctx.state
    if args.vendor not in state.vendors:
        raise ToolError(f"unknown vendor {args.vendor}")
    if args.amount <= 0:
        raise ToolError("amounts are positive; a credit memo says what it corrects instead")
    if args.po is not None and args.po not in state.purchase_orders:
        raise ToolError(f"unknown PO {args.po}")
    specs: list[EventSpec] = []
    status = "received"
    if args.kind == "credit_memo":
        original = state.invoices.get(args.supersedes or "")
        if original is None or original.vendor != args.vendor:
            raise ToolError(f"credit memo must correct an invoice of {args.vendor}")
        if original.status in ("paid", "cancelled"):
            raise ToolError(f"{original.id} is {original.status}; nothing left to cancel")
        status = "applied"
    numbers = [int(i.id.split("-")[1]) for i in state.invoices.values()]
    iid = f"INV-{max(numbers, default=1000) + 1}"
    invoice = {
        "id": iid,
        "vendor": args.vendor,
        "number": args.number,
        "po": args.po,
        "amount": args.amount,
        "dimension": args.dimension,
        "received_on": state.day,
        "due_date": state.day + args.due_in_days,
        "kind": args.kind,
        "supersedes": args.supersedes,
        "status": status,
    }
    specs.append(("invoice.received", {"invoice": invoice, "message": args.message}))
    if args.kind == "credit_memo":
        specs.append(("invoice.cancelled", {"invoice": args.supersedes, "by": iid}))
    return specs


def _record_portal(ctx: Ctx, args: ChangeRef) -> list[EventSpec]:
    """A change submitted through the authenticated vendor portal carries its own evidence."""
    state = ctx.state
    cr = _held_change(state, args.change)
    if cr.channel != "portal":
        raise ToolError(f"{cr.id} came by {cr.channel}, not the portal")
    evidence = {
        "id": f"EVD-{len(state.evidence) + 1:04d}",
        "change_request": cr.id,
        "channel": "portal",
        "direction": "inbound",
        "received_on": state.day,
        "status": "answered",
        "confirms": True,
        "authenticated": True,
        "message": cr.message,
    }
    return [("evidence.created", {"evidence": evidence})]


def _apply_cash(ctx: Ctx, args: CashArgs) -> list[EventSpec]:
    state = ctx.state
    txn = state.bank_transactions.get(args.transaction)
    if txn is None or txn.amount <= 0 or txn.reconciled or txn.returns:
        raise ToolError(f"{args.transaction} is not an unapplied deposit")
    if args.customer is not None and args.customer not in state.customers:
        raise ToolError(f"unknown customer {args.customer}")
    return money_in.apply(state, txn.id, args.customer, args.invoices)


def _reverse_cash(ctx: Ctx, args: TransactionRef) -> list[EventSpec]:
    txn = ctx.state.bank_transactions.get(args.transaction)
    if txn is None or txn.returns is None or txn.reconciled:
        raise ToolError(f"{args.transaction} is not an unreconciled returned deposit")
    return money_in.reverse(ctx.state, txn.id)


def _refund(status: str) -> Effect:
    def effect(ctx: Ctx, args: RefundArgs) -> list[EventSpec]:
        state = ctx.state
        if args.customer not in state.customers:
            raise ToolError(f"unknown customer {args.customer}")
        credit = money_in.credit_balance(state, args.customer)
        if not 0 < args.amount <= credit:
            raise ToolError(f"{args.customer} has a credit of {credit}, not {args.amount}")
        return money_in.refund(
            state,
            args.customer,
            args.amount,
            args.destination_account,
            args.reason,
            args.message,
            status,
        )

    return effect


@dataclass(frozen=True)
class ToolSpec:
    stage: Stage
    args: type[BaseModel]
    effects: dict[Decision, Effect]  # decisions without an effect change nothing


TOOLS: dict[str, ToolSpec] = {
    "invoices.validate": ToolSpec(
        "invoice.match",
        InvoiceRef,
        {
            "allow": _validate,
            "hold": _validate_stopped("invoice.held"),
            "block": _validate_stopped("invoice.rejected"),
        },
    ),
    "approvals.request": ToolSpec(
        "pre_approve", InvoiceRef, {"allow": _request_approval, "escalate": _escalate_approval}
    ),
    "approvals.decide": ToolSpec("pre_approve", DecideArgs, {"allow": _decide}),
    "payments.schedule": ToolSpec("schedule", ScheduleArgs, {"allow": _schedule}),
    "payments.execute": ToolSpec("pre_execute", InvoiceRef, {"allow": _execute}),
    "payments.submit": ToolSpec("submit", PaymentRef, {"allow": _submit}),
    "payments.retry": ToolSpec("retry", PaymentRef, {"allow": _retry}),
    "cash.apply": ToolSpec("journal", CashArgs, {"allow": _apply_cash}),
    "cash.reverse": ToolSpec("journal", TransactionRef, {"allow": _reverse_cash}),
    "refunds.issue": ToolSpec(
        "refund",
        RefundArgs,
        {
            "allow": _refund("refunded"),
            "hold": _refund("held"),
            "escalate": _refund("held"),
            "block": _refund("rejected"),
        },
    ),
    "payments.query_status": ToolSpec("retry", PaymentRef, {"allow": _query_status}),
    "ledger.reconcile": ToolSpec("journal", TransactionRef, {"allow": _reconcile}),
    "vendors.change_request": ToolSpec(
        "change_request",
        ChangeRequestArgs,
        {
            "allow": _new_change,
            "hold": _stop_change("held"),
            "escalate": _stop_change("held"),
            "block": _stop_change("rejected"),
        },
    ),
    "vendors.apply_change": ToolSpec(
        "change_request", ChangeRef, {"allow": _apply_held, "block": _reject_held}
    ),
    "evidence.request_callback": ToolSpec(
        "verification", CallbackArgs, {"allow": _request_callback}
    ),
    "invoices.receive": ToolSpec("intake", InvoiceArgs, {"allow": _receive_invoice}),
    "evidence.record_portal": ToolSpec("verification", ChangeRef, {"allow": _record_portal}),
    "evidence.record_inbound": ToolSpec(
        "verification", InboundEvidenceArgs, {"allow": _record_inbound}
    ),
}


# --- The Tools layer ------------------------------------------------------------------------


class GatedTools:
    """The only way to change twin state. Implements contracts.interfaces.Tools."""

    def __init__(self, run: Run, guard: Guard) -> None:
        self.run = run
        self.guard = guard
        self.calls = 0

    @property
    def view(self) -> State:
        return self.run.state

    def call(self, actor: Actor, name: str, args: BaseModel) -> ToolResult:
        spec = TOOLS.get(name)
        if spec is None:
            raise KeyError(f"unknown tool {name!r}")
        if not isinstance(args, spec.args):
            raise TypeError(f"{name} takes {spec.args.__name__}, got {type(args).__name__}")
        self.calls += 1
        state = self.run.state
        # args is an already-validated spec.args model, so don't revalidate its dump (hot path)
        action = construct(Action, {"actor": actor, "name": name, "args": args.model_dump()})
        verdict = self.guard.check(state, action, spec.stage)
        recorded = self.run.emit(
            "gate.verdict",
            {
                "tool": name,
                "stage": spec.stage,
                "args": action.args,
                "verdict": verdict.model_dump(mode="json"),
            },
            actor=actor.id,
        )
        effect = spec.effects.get(verdict.decision)
        if effect is None:
            return ToolResult(ok=False, verdict=verdict, events=[recorded.id])
        try:
            specs = effect(Ctx(state, actor, verdict), args)
        except ToolError as err:
            return ToolResult(
                ok=False, verdict=verdict, data={"error": str(err)}, events=[recorded.id]
            )
        emitted = [
            self.run.emit(kind, payload, actor=actor.id, caused_by=[recorded.id])
            for kind, payload in specs
        ]
        return ToolResult(
            ok=verdict.decision == "allow",
            verdict=verdict,
            data={"events": [e.kind for e in emitted]},
            events=[recorded.id] + [e.id for e in emitted],
        )
