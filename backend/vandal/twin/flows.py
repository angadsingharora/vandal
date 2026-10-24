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
from typing import Any

from pydantic import BaseModel, ConfigDict

from vandal.contracts.controls import Decision, Stage
from vandal.contracts.entities import Actor, ApprovedInstruction
from vandal.contracts.interfaces import Action, Guard, ToolResult
from vandal.contracts.verdicts import Verdict
from vandal.twin import bank, ledger
from vandal.twin.facts import current_account
from vandal.twin.state import State
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


class DecideArgs(_Args):
    request: str
    approve: bool
    reason: str = ""


class TransactionRef(_Args):
    transaction: str


class ChangeRequestArgs(_Args):
    """A vendor-master change as the Operator extracted it from an inbound message."""

    vendor: str
    channel: str
    sender: str
    message: str | None = None
    routing: str
    account: str


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
    return bank.submit(state, pay.id) + [("journal.posted", {"entry": je.model_dump()})]


def _reconcile(ctx: Ctx, args: TransactionRef) -> list[EventSpec]:
    txn = ctx.state.bank_transactions.get(args.transaction)
    if txn is None or txn.reconciled:
        raise ToolError(f"{args.transaction} is unknown or already reconciled")
    if txn.payment is None or ctx.state.payments[txn.payment].status != "settled":
        raise ToolError(f"{args.transaction} matches no settled payment")
    return [("bank.reconciled", {"transaction": txn.id, "payment": txn.payment})]


def _change_request(state: State, args: ChangeRequestArgs, status: str) -> dict[str, Any]:
    if args.vendor not in state.vendors:
        raise ToolError(f"unknown vendor {args.vendor}")
    return {
        "id": f"CR-{len(state.change_requests) + 1:04d}",
        "vendor": args.vendor,
        "proposed": {"routing": args.routing, "account": args.account},
        "channel": args.channel,
        "sender": args.sender,
        "message": args.message,
        "received_on": state.day,
        "status": status,
    }


def _apply_change(ctx: Ctx, args: ChangeRequestArgs) -> list[EventSpec]:
    """v0: the vendor master is updated as requested, with no verification."""
    state = ctx.state
    request = _change_request(state, args, "open")
    superseded = [
        a.id
        for a in state.vendor_bank_accounts.values()
        if a.vendor == args.vendor and a.status in ("verified", "unverified")
    ]
    account = {
        "id": f"BA-{len(state.vendor_bank_accounts) + 1:04d}",
        "vendor": args.vendor,
        "routing": args.routing,
        "account": args.account,
        "status": "unverified",
        "source": f"change_request:{request['id']}",
    }
    return [
        ("change_request.created", {"request": request}),
        (
            "vendor.bank_changed",
            {"request": request["id"], "account": account, "superseded": superseded},
        ),
    ]


def _stop_change(status: str) -> Effect:
    def effect(ctx: Ctx, args: ChangeRequestArgs) -> list[EventSpec]:
        return [
            (
                "change_request.created",
                {"request": _change_request(ctx.state, args, status), "checks": ctx.verdict.fired},
            )
        ]

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
    "ledger.reconcile": ToolSpec("journal", TransactionRef, {"allow": _reconcile}),
    "vendors.change_request": ToolSpec(
        "change_request",
        ChangeRequestArgs,
        {
            "allow": _apply_change,
            "hold": _stop_change("held"),
            "escalate": _stop_change("held"),
            "block": _stop_change("rejected"),
        },
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
        action = Action(actor=actor, name=name, args=args.model_dump())
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
