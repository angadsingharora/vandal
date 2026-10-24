"""R11: money in. Deposits, cash application, customer credits, and refunds (DESIGN 5.2).

  Deposit (bank feed) -> applied to customer invoice(s) -> posted -> credit? -> refund requested
  -> refunded

  cash application  a deposit's remittance memo names its customer, or the invoices it pays.
                    It pays the invoices it names first, then the customer's oldest open ones;
                    what's left is a customer credit. A deposit that names no known customer
                    goes to suspense. One deposit can pay several invoices, or part of one.
  provisional       a deposit can post before it clears (a check, a debit that can still come
                    back). Cash application treats it like any other; the bank says later
                    whether it cleared or came back, and a return reverses the application.
  refunds           go out the same day from the operating account, against the customer's
                    credit. v0 has no rule on where a refund may go, or whether the money
                    behind the credit has cleared.

Functions return (kind, payload) event specs, like twin/bank.py.
"""

from __future__ import annotations

import re
from typing import Any

from vandal.contracts.entities import Cents, IncomingPayment
from vandal.twin import ledger
from vandal.twin.state import State

AR_CONTROL = "1200"
CUSTOMER_CREDITS = "2100"
SUSPENSE = "2900"

EventSpec = tuple[str, dict[str, Any]]
_CUSTOMER = re.compile(r"\bC-\d{3}\b")
_INVOICE = re.compile(r"\bAR-\d{4}\b")


def identify(state: State, memo: str) -> tuple[str | None, list[str]]:
    """The customer and invoices a remittance memo names. An invoice also names its customer."""
    invoices = [i for i in _INVOICE.findall(memo) if i in state.customer_invoices]
    customers = [c for c in _CUSTOMER.findall(memo) if c in state.customers]
    if not customers and invoices:
        customers = [state.customer_invoices[invoices[0]].customer]
    return (customers[0] if customers else None), invoices


def open_balance(state: State, customer: str) -> Cents:
    return sum(
        i.amount - i.paid for i in state.customer_invoices.values() if i.customer == customer
    )


def allocate(state: State, customer: str, amount: Cents, named: list[str]) -> dict[str, Cents]:
    """Named invoices first, then the customer's oldest open ones."""
    open_ = [
        i for i in state.customer_invoices.values() if i.customer == customer and i.paid < i.amount
    ]
    order = sorted(open_, key=lambda i: (i.id not in named, i.due_date, i.id))
    out: dict[str, Cents] = {}
    left = amount
    for inv in order:
        if left <= 0:
            break
        pay = min(left, inv.amount - inv.paid)
        out[inv.id] = pay
        left -= pay
    return out


def _payments_of(state: State, customer: str) -> list[IncomingPayment]:
    return [p for p in state.incoming_payments.values() if p.payer == customer and not p.returned]


def credit_balance(state: State, customer: str, cleared_only: bool = False) -> Cents:
    """What the customer is owed: credits from its deposits, less what was refunded. With
    `cleared_only`, credits behind deposits that haven't cleared don't count."""
    credits = sum(
        p.credit
        for p in _payments_of(state, customer)
        if not cleared_only or state.bank_transactions[p.bank_transaction].cleared
    )
    refunded = sum(
        r.amount
        for r in state.refunds.values()
        if r.customer == customer and r.status == "refunded"
    )
    return credits - refunded


def credit_sources(state: State, customer: str) -> list[IncomingPayment]:
    """The deposits behind a customer's credit, newest first."""
    return sorted(
        (p for p in _payments_of(state, customer) if p.credit > 0),
        key=lambda p: state.bank_transactions[p.bank_transaction].posted_on,
        reverse=True,
    )


def apply(
    state: State, transaction: str, customer: str | None, named: list[str]
) -> list[EventSpec]:
    txn = state.bank_transactions[transaction]
    applied = allocate(state, customer, txn.amount, named) if customer else {}
    credit = txn.amount - sum(applied.values())
    payment = {
        "id": f"IN-{len(state.incoming_payments) + 1:04d}",
        "bank_transaction": txn.id,
        "payer": customer,
        "source_account": txn.counterparty_account or "unknown",
        "amount": txn.amount,
        "remittance": txn.memo,
        "applied": applied,
        "credit": credit,
    }
    cash = state.bank_accounts[txn.bank_account].gl_account
    credits = {AR_CONTROL: sum(applied.values())} if applied else {}
    if credit:
        credits[CUSTOMER_CREDITS if customer else SUSPENSE] = credit
    je = ledger.entry(
        ledger.next_entry_id(state),
        state.day,
        f"Cash application {payment['id']} ({txn.id})",
        {cash: txn.amount},
        credits,
    )
    return [
        ("cash.applied", {"payment": payment}),
        ("journal.posted", {"entry": je.model_dump()}),
    ]


def reverse(state: State, transaction: str) -> list[EventSpec]:
    """A deposit came back: undo its application. Invoices reopen; a credit already refunded
    leaves the customer owing it (Customer Credits goes negative)."""
    txn = state.bank_transactions[transaction]
    original = next(
        p for p in state.incoming_payments.values() if p.bank_transaction == txn.returns
    )
    cash = state.bank_accounts[txn.bank_account].gl_account
    debits = {AR_CONTROL: sum(original.applied.values())} if original.applied else {}
    if original.credit:
        debits[CUSTOMER_CREDITS if original.payer else SUSPENSE] = original.credit
    je = ledger.entry(
        ledger.next_entry_id(state),
        state.day,
        f"Returned deposit {txn.returns} ({original.id})",
        debits,
        {cash: -txn.amount},
    )
    return [
        ("cash.reversed", {"payment": original.id, "transaction": txn.id}),
        ("journal.posted", {"entry": je.model_dump()}),
    ]


def refund(
    state: State,
    customer: str,
    amount: Cents,
    destination: str,
    reason: str,
    message: str | None,
    status: str,
    account: str = "CB-OPER",
) -> list[EventSpec]:
    rid = f"RF-{len(state.refunds) + 1:04d}"
    record = {
        "id": rid,
        "customer": customer,
        "amount": amount,
        "destination_account": destination,
        "reason": reason,
        "message": message,
        "requested_on": state.day,
        "status": status,
    }
    if status != "refunded":
        return [("refund.stopped", {"refund": record})]
    txn = {
        "id": f"BT-{len(state.bank_transactions) + 1:04d}",
        "bank_account": account,
        "amount": -amount,
        "posted_on": state.day,
        "refund": rid,
        "counterparty_account": destination,
        "reconciled": True,  # the refund is its own match
    }
    cash = state.bank_accounts[account].gl_account
    je = ledger.entry(
        ledger.next_entry_id(state),
        state.day,
        f"Refund {rid} to {customer}",
        {CUSTOMER_CREDITS: amount},
        {cash: amount},
    )
    return [
        ("refund.issued", {"refund": record, "transaction": txn}),
        ("journal.posted", {"entry": je.model_dump()}),
    ]
