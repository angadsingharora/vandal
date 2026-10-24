"""R1: apply(state, event) -> state, a pure function, plus the in-place path search uses.

Each event kind has one handler. A handler changes the state it's given through
State.put()/update() only, never by editing an entity. apply() hands it a fresh clone, so callers
keep every earlier state; fold() clones once per run and then applies in place. Later slices
register their own kinds (flows in R2, bank in R2, ...).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from vandal.contracts.entities import (
    Approval,
    ApprovalRequest,
    BankFault,
    BankSubmission,
    BankTransaction,
    Evidence,
    Invoice,
    JournalEntry,
    Payment,
    PaymentInstruction,
    VendorBankAccount,
    VendorChangeRequest,
    VendorContact,
)
from vandal.contracts.events import Event
from vandal.twin.state import State

Handler = Callable[[State, Event], None]
HANDLERS: dict[str, Handler] = {}


def handles(kind: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        if kind in HANDLERS:
            raise ValueError(f"duplicate handler for {kind!r}")
        HANDLERS[kind] = fn
        return fn

    return register


def apply_in_place(state: State, event: Event) -> None:
    """Apply one event to a state the caller owns (a fresh clone). If a handler raises, the
    state may be half-applied: discard it."""
    if event.seq != len(state.events):
        raise ValueError(f"event {event.id} has seq {event.seq}, expected {len(state.events)}")
    handler = HANDLERS.get(event.kind)
    if handler is None:
        raise ValueError(f"no handler for event kind {event.kind!r}")
    handler(state, event)
    state.events.append(event)


def apply(state: State, event: Event) -> State:
    nxt = state.clone()
    apply_in_place(nxt, event)
    return nxt


def fold(state: State, events: Iterable[Event]) -> State:
    """One clone per run, then in place: the hot path for search and replay."""
    run = state.clone()
    for event in events:
        apply_in_place(run, event)
    return run


@handles("clock.tick")
def _tick(state: State, event: Event) -> None:
    days = int(event.payload.get("days", 1))
    if days < 1:
        raise ValueError("clock.tick must advance at least one business day")
    state.day += days


@handles("invoice.received")
def _invoice_received(state: State, event: Event) -> None:
    invoice = Invoice.model_validate(event.payload["invoice"])
    if invoice.id in state.invoices:
        raise ValueError(f"{invoice.id} already exists")
    state.put("invoices", invoice)


@handles("gate.verdict")
def _gate_verdict(state: State, event: Event) -> None:
    """Recorded for the evidence log; the verdict itself changes nothing."""


@handles("invoice.validated")
def _invoice_validated(state: State, event: Event) -> None:
    state.update("invoices", event.payload["invoice"], status="validated")


@handles("invoice.held")
def _invoice_held(state: State, event: Event) -> None:
    state.update("invoices", event.payload["invoice"], status="held")


@handles("invoice.rejected")
def _invoice_rejected(state: State, event: Event) -> None:
    state.update("invoices", event.payload["invoice"], status="rejected")


@handles("approval.requested")
def _approval_requested(state: State, event: Event) -> None:
    state.put("approval_requests", ApprovalRequest.model_validate(event.payload["request"]))


@handles("approval.granted")
def _approval_granted(state: State, event: Event) -> None:
    approval = Approval.model_validate(event.payload["approval"])
    state.put("approvals", approval)
    state.update("invoices", approval.subject, status="approved")
    if request := event.payload.get("request"):
        state.update("approval_requests", request, status="approved", decided_by=approval.approver)


@handles("approval.denied")
def _approval_denied(state: State, event: Event) -> None:
    req = state.update(
        "approval_requests",
        event.payload["request"],
        status="denied",
        decided_by=event.payload["by"],
        reason=event.payload.get("reason", ""),
    )
    state.update("invoices", req.subject, status="held")


@handles("invoice.scheduled")
def _invoice_scheduled(state: State, event: Event) -> None:
    state.update(
        "invoices",
        event.payload["invoice"],
        status="scheduled",
        scheduled_for=event.payload["pay_on"],
    )


@handles("instruction.built")
def _instruction_built(state: State, event: Event) -> None:
    state.put(
        "payment_instructions", PaymentInstruction.model_validate(event.payload["instruction"])
    )
    state.put("payments", Payment.model_validate(event.payload["payment"]))


@handles("payment.submitted")
def _payment_submitted(state: State, event: Event) -> None:
    pay = state.payments[event.payload["payment"]]
    state.update(
        "payments",
        pay.id,
        status="submitted",
        attempts=pay.attempts + 1,
        submitted_on=state.day,
        bank_status="unknown",  # a status answered before this attempt says nothing about it
    )
    invoice = state.payment_instructions[pay.instruction].invoice
    state.update("invoices", invoice, status="paid")


@handles("bank.ack")
def _bank_ack(state: State, event: Event) -> None:
    """Only a payment waiting on its ack moves; a late or duplicate ack changes nothing."""
    if state.payments[event.payload["payment"]].status == "submitted":
        state.update("payments", event.payload["payment"], status="acknowledged")


@handles("bank.processed")
def _bank_processed(state: State, event: Event) -> None:
    state.put("bank_submissions", BankSubmission.model_validate(event.payload["submission"]))


@handles("bank.fault_armed")
def _bank_fault_armed(state: State, event: Event) -> None:
    state.put("bank_faults", BankFault.model_validate(event.payload["fault"]))


@handles("bank.fault_used")
def _bank_fault_used(state: State, event: Event) -> None:
    state.update("bank_faults", event.payload["fault"], status="used")


@handles("bank.status_reported")
def _bank_status_reported(state: State, event: Event) -> None:
    state.update("payments", event.payload["payment"], bank_status=event.payload["status"])


@handles("bank.settled")
def _bank_settled(state: State, event: Event) -> None:
    txn = BankTransaction.model_validate(event.payload["transaction"])
    state.put("bank_transactions", txn)
    account = state.bank_accounts[txn.bank_account]
    state.update("bank_accounts", account.id, balance=account.balance + txn.amount)
    if txn.payment:
        state.update("payments", txn.payment, status="settled", settled_on=state.day)
    if txn.submission:
        state.update("bank_submissions", txn.submission, status="settled")


@handles("bank.reconciled")
def _bank_reconciled(state: State, event: Event) -> None:
    state.update("bank_transactions", event.payload["transaction"], reconciled=True)


@handles("journal.posted")
def _journal_posted(state: State, event: Event) -> None:
    state.journal.append(JournalEntry.model_validate(event.payload["entry"]))


@handles("channel.received")
def _channel_received(state: State, event: Event) -> None:
    """An inbound message (email, call, agent message). Logged so chains can cite it."""


@handles("change_request.created")
def _change_request_created(state: State, event: Event) -> None:
    state.put("change_requests", VendorChangeRequest.model_validate(event.payload["request"]))


@handles("vendor.bank_changed")
def _vendor_bank_changed(state: State, event: Event) -> None:
    """Applies a change request to the vendor master: the new account becomes current."""
    for old in event.payload["superseded"]:
        state.update("vendor_bank_accounts", old, status="superseded")
    state.put("vendor_bank_accounts", VendorBankAccount.model_validate(event.payload["account"]))
    state.update("change_requests", event.payload["request"], status="applied")


@handles("vendor.contact_changed")
def _vendor_contact_changed(state: State, event: Event) -> None:
    for old in event.payload["ended"]:
        state.update("vendor_contacts", old, valid_to=state.day)
    state.put("vendor_contacts", VendorContact.model_validate(event.payload["contact"]))
    state.update("change_requests", event.payload["request"], status="applied")


@handles("change_request.rejected")
def _change_request_rejected(state: State, event: Event) -> None:
    state.update("change_requests", event.payload["request"], status="rejected")


@handles("evidence.created")
def _evidence_created(state: State, event: Event) -> None:
    evidence = Evidence.model_validate(event.payload["evidence"])
    state.put("evidence", evidence)
    cr = state.change_requests[evidence.change_request]
    state.update("change_requests", cr.id, evidence=[*cr.evidence, evidence.id])


@handles("callback.answered")
def _callback_answered(state: State, event: Event) -> None:
    state.update(
        "evidence",
        event.payload["evidence"],
        status="answered",
        confirms=bool(event.payload["confirms"]),
    )


@handles("invoice.cancelled")
def _invoice_cancelled(state: State, event: Event) -> None:
    state.update("invoices", event.payload["invoice"], status="cancelled")
