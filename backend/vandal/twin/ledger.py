"""R2: append-only journal entries (DESIGN 12) and reversal entries.

Builders only produce entries; posting is the `journal.posted` event. The reducer never checks
balance, so INV-1 can catch a bad entry instead of the twin silently refusing it.
"""

from __future__ import annotations

from vandal.contracts.entities import Cents, JournalEntry, JournalLine, SimDay
from vandal.twin.state import State

AP_CONTROL = "2000"
VENDOR_OVERPAYMENT = "1310"
MISDIRECTED_RECEIVABLE = "1300"


def next_entry_id(state: State, offset: int = 0) -> str:
    return f"JE-{len(state.journal) + 1 + offset:04d}"


def entry(
    eid: str, day: SimDay, memo: str, debits: dict[str, Cents], credits: dict[str, Cents]
) -> JournalEntry:
    lines = [JournalLine(account=a, debit=c) for a, c in debits.items()]
    lines += [JournalLine(account=a, credit=c) for a, c in credits.items()]
    return JournalEntry(id=eid, posted_on=day, lines=lines, memo=memo)


def invoice_approved(eid: str, day: SimDay, invoice: str, expense: str, amount: Cents):
    """Dr Expense (dimension) / Cr AP."""
    return entry(eid, day, f"Approve {invoice}", {expense: amount}, {AP_CONTROL: amount})


def payment_submitted(eid: str, day: SimDay, payment: str, cash: str, amount: Cents):
    """Dr AP / Cr Cash."""
    return entry(eid, day, f"Submit {payment}", {AP_CONTROL: amount}, {cash: amount})


def duplicate_settlement(
    eid: str, day: SimDay, txn: str, payment: str, cash: str, amount: Cents
) -> JournalEntry:
    """Dr Vendor Overpayment Receivable / Cr Cash: the second debit the bank feed shows."""
    return entry(
        eid,
        day,
        f"Duplicate settlement {txn} of {payment}",
        {VENDOR_OVERPAYMENT: amount},
        {cash: amount},
    )


def misdirected(eid: str, day: SimDay, payment: str, amount: Cents) -> JournalEntry:
    """Dr Misdirected Payment Receivable / Cr AP: the money went to the wrong place, so the
    company is owed it back, and it still owes the vendor (DESIGN 12)."""
    return entry(
        eid, day, f"Misdirected {payment}", {MISDIRECTED_RECEIVABLE: amount}, {AP_CONTROL: amount}
    )


def recalled(eid: str, day: SimDay, payment: str, cash: str, amount: Cents) -> JournalEntry:
    """Dr Cash / Cr Misdirected Payment Receivable: the bank recalled it before it settled."""
    return entry(eid, day, f"Recalled {payment}", {cash: amount}, {MISDIRECTED_RECEIVABLE: amount})


def reversal(eid: str, day: SimDay, original: JournalEntry) -> JournalEntry:
    """Swap every line. Corrections are a reversal plus a replacement, never an edit."""
    lines = [
        JournalLine(account=ln.account, debit=ln.credit, credit=ln.debit) for ln in original.lines
    ]
    return JournalEntry(
        id=eid,
        posted_on=day,
        lines=lines,
        memo=f"Reverse {original.id}",
        reverses_entry_id=original.id,
    )


def balance(state: State, account: str) -> Cents:
    """Debit-positive balance of a GL account."""
    return sum(
        ln.debit - ln.credit for je in state.journal for ln in je.lines if ln.account == account
    )
