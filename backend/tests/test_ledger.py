from __future__ import annotations

from vandal.twin import ledger
from vandal.twin.seed import seed_state


def test_reversal_nets_to_zero() -> None:
    original = ledger.invoice_approved("JE-0002", 0, "INV-1", "5100", 12_345)
    rev = ledger.reversal("JE-0003", 1, original)
    assert rev.reverses_entry_id == "JE-0002"
    net: dict[str, int] = {}
    for je in (original, rev):
        for ln in je.lines:
            net[ln.account] = net.get(ln.account, 0) + ln.debit - ln.credit
    assert set(net.values()) == {0}


def test_builders_balance() -> None:
    for je in (
        ledger.invoice_approved("JE-1", 0, "INV-1", "5100", 500),
        ledger.payment_submitted("JE-2", 0, "PAY-1", "1000", 500),
    ):
        assert sum(ln.debit for ln in je.lines) == sum(ln.credit for ln in je.lines)


def test_opening_balances() -> None:
    s = seed_state()
    assert ledger.balance(s, "1000") == 180_000_000
    assert ledger.balance(s, ledger.AP_CONTROL) == 0
