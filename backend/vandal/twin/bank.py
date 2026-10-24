"""R2: bank simulator. submit -> ack; settlement at T+1 as a BankTransaction. Faults land in R10.

Functions return (kind, payload) event specs; the caller appends them so they get ids and seqs.
"""

from __future__ import annotations

from typing import Any

from vandal.twin.state import State

OPERATING = "CB-OPER"
SETTLEMENT_LAG = 1  # business days

EventSpec = tuple[str, dict[str, Any]]


def submit(state: State, payment: str) -> list[EventSpec]:
    return [("payment.submitted", {"payment": payment}), ("bank.ack", {"payment": payment})]


def settle_due(state: State) -> list[EventSpec]:
    """Acknowledged payments submitted at least SETTLEMENT_LAG days ago settle today."""
    specs: list[EventSpec] = []
    n = len(state.bank_transactions)
    for pay in state.payments.values():
        if pay.status != "acknowledged" or pay.submitted_on is None:
            continue
        if state.day - pay.submitted_on < SETTLEMENT_LAG:
            continue
        instr = state.payment_instructions[pay.instruction]
        n += 1
        specs.append(
            (
                "bank.settled",
                {
                    "transaction": {
                        "id": f"BT-{n:04d}",
                        "bank_account": OPERATING,
                        "amount": -instr.amount,
                        "posted_on": state.day,
                        "payment": pay.id,
                        "counterparty_account": instr.payee_account,
                    }
                },
            )
        )
    return specs
