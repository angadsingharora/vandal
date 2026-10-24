"""R2: append-only journal entries (DESIGN 12) and reversal entries.

Builders only produce entries; posting is the `journal.posted` event. The reducer never checks
balance, so INV-1 can catch a bad entry instead of the twin silently refusing it.
"""

from __future__ import annotations

from vandal.contracts.entities import Cents, JournalEntry, JournalLine, SimDay
from vandal.twin.state import State

AP_CONTROL = "2000"


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
