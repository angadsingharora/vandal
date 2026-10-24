"""R2/R10: bank simulator. submit -> ack; settlement at T+1 as a BankTransaction.

Functions return (kind, payload) event specs; the caller appends them so they get ids and seqs.

R10 faults (DESIGN 5.3), each armed by a `fault` move and used by the next submission:

  timeout        the submission never reaches the bank: no ack, nothing to settle
  drop_ack       the bank processes it, but the ack is lost
  duplicate_ack  the ack arrives twice
  delay(n)       settles n days late
  feed_delay(n)  the bank feed posts nothing for n days (settlements wait)

The bank deduplicates a submission only if it carries an idempotency key that an earlier one
already used. In v0 the Operator sends no key, so a retry after a lost ack pays twice.
"""

from __future__ import annotations

from typing import Any

from vandal.contracts.entities import BankFault
from vandal.twin.state import State

OPERATING = "CB-OPER"
SETTLEMENT_LAG = 1  # business days
CLEARING_DAYS = 2  # a provisional deposit clears, or comes back, this many days later
RECALL_DAYS = 2  # the beneficiary's bank answers a recall this many days later
FAULT_KINDS = ("timeout", "drop_ack", "duplicate_ack", "delay", "feed_delay")

EventSpec = tuple[str, dict[str, Any]]


def arm(state: State, kind: str, days: int = 0) -> EventSpec:
    fault = {
        "id": f"BF-{len(state.bank_faults) + 1:04d}",
        "kind": kind,
        "days": days,
        "armed_on": state.day,
    }
    return ("bank.fault_armed", {"fault": fault})


def _armed(state: State, *kinds: str) -> BankFault | None:
    return next(
        (f for f in state.bank_faults.values() if f.status == "armed" and f.kind in kinds), None
    )


def submit(state: State, payment: str, key: str | None = None) -> list[EventSpec]:
    specs: list[EventSpec] = [("payment.submitted", {"payment": payment, "key": key})]
    if key is not None:
        original = next(
            (s for s in state.bank_submissions.values() if s.idempotency_key == key), None
        )
        if original is not None:  # a reused key: the bank answers for the original
            return specs + [("bank.ack", {"payment": payment, "deduplicated": original.id})]
    fault = _armed(state, "timeout", "drop_ack", "duplicate_ack", "delay")
    if fault is not None:
        specs.append(("bank.fault_used", {"fault": fault.id, "payment": payment}))
        if fault.kind == "timeout":
            return specs
    pay = state.payments[payment]
    instr = state.payment_instructions[pay.instruction]
    delay = fault.days if fault is not None and fault.kind == "delay" else 0
    submission = {
        "id": f"BS-{len(state.bank_submissions) + 1:04d}",
        "payment": payment,
        "amount": instr.amount,
        "payee_account": instr.payee_account,
        "idempotency_key": key,
        "submitted_on": state.day,
        "settle_on": state.day + SETTLEMENT_LAG + delay,
    }
    specs.append(("bank.processed", {"submission": submission}))
    if fault is not None and fault.kind == "drop_ack":
        return specs
    specs.append(("bank.ack", {"payment": payment}))
    if fault is not None and fault.kind == "duplicate_ack":
        specs.append(("bank.ack", {"payment": payment}))
    return specs


def status(state: State, payment: str) -> EventSpec:
    """The bank's answer to a status inquiry: did any submission for this payment arrive?"""
    processed = any(s.payment == payment for s in state.bank_submissions.values())
    return (
        "bank.status_reported",
        {"payment": payment, "status": "processed" if processed else "not_found"},
    )


def deposit(
    state: State, amount: int, source: str, memo: str, cleared: bool, comes_back: bool
) -> EventSpec:
    """Money arrives on the feed. A provisional one (`cleared=False`) resolves later: it
    clears, or (`comes_back`) the bank returns it."""
    txn = {
        "id": f"BT-{len(state.bank_transactions) + 1:04d}",
        "bank_account": OPERATING,
        "amount": amount,
        "posted_on": state.day,
        "counterparty_account": source,
        "memo": memo,
        "cleared": cleared,
    }
    pending = None
    if not cleared:
        pending = {
            "id": f"BD-{len(state.bank_deposits) + 1:04d}",
            "transaction": txn["id"],
            "outcome": "return" if comes_back else "clear",
            "on": state.day + CLEARING_DAYS,
        }
    return ("bank.deposit", {"transaction": txn, "pending": pending})


def settle_due(state: State) -> list[EventSpec]:
    """Processed submissions whose settlement day has come settle today, unless the feed is
    down."""
    specs: list[EventSpec] = []
    for f in state.bank_faults.values():
        if f.status == "armed" and f.kind == "feed_delay":
            if state.day < f.armed_on + f.days:
                return specs
            specs.append(("bank.fault_used", {"fault": f.id}))
    n = len(state.bank_transactions)
    for dep in state.bank_deposits.values():
        if dep.status != "pending" or dep.on > state.day:
            continue
        if dep.outcome == "clear":
            specs.append(("bank.deposit_cleared", {"deposit": dep.id}))
            continue
        original = state.bank_transactions[dep.transaction]
        n += 1
        returned = {
            "id": f"BT-{n:04d}",
            "bank_account": original.bank_account,
            "amount": -original.amount,
            "posted_on": state.day,
            "counterparty_account": original.counterparty_account,
            "memo": f"Returned deposit {original.id}",
            "returns": original.id,
        }
        specs.append(("bank.deposit_returned", {"deposit": dep.id, "transaction": returned}))
    for sub in state.bank_submissions.values():
        if sub.status != "processed" or sub.settle_on > state.day:
            continue
        n += 1
        specs.append(
            (
                "bank.settled",
                {
                    "transaction": {
                        "id": f"BT-{n:04d}",
                        "bank_account": OPERATING,
                        "amount": -sub.amount,
                        "posted_on": state.day,
                        "payment": sub.payment,
                        "submission": sub.id,
                        "counterparty_account": sub.payee_account,
                    }
                },
            )
        )
    return specs


def answer_recalls(state: State) -> list[EventSpec]:
    """Recalls the beneficiary's bank answers today. A recall succeeds only if the money hasn't
    settled yet: the submission is cancelled and never settles. Settlement is T+1 and a recall
    takes RECALL_DAYS, so most recalls fail unless settlement was delayed."""
    specs: list[EventSpec] = []
    for pay in state.payments.values():
        if pay.recall != "requested" or pay.recall_requested_on is None:
            continue
        if state.day - pay.recall_requested_on < RECALL_DAYS:
            continue
        open_subs = [
            s.id
            for s in state.bank_submissions.values()
            if s.payment == pay.id and s.status == "processed"
        ]
        specs.append(
            (
                "bank.recall_answered",
                {
                    "payment": pay.id,
                    "outcome": "succeeded" if open_subs else "failed",
                    "cancelled": open_subs,
                },
            )
        )
    return specs
