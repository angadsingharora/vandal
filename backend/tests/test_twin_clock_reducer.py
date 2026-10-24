from __future__ import annotations

from datetime import date

import pytest

from vandal.contracts.events import Event
from vandal.twin.clock import BusinessClock
from vandal.twin.reducer import apply, fold
from vandal.twin.seed import seed_state


def ev(seq: int, kind: str, **payload) -> Event:
    return Event(id=f"EV-{seq:06d}", seq=seq, day=0, kind=kind, actor="system", payload=payload)


def test_clock_skips_weekends() -> None:
    clock = BusinessClock(date(2026, 7, 1))  # a Wednesday
    assert clock.date_of(0) == date(2026, 7, 1)
    assert clock.date_of(2) == date(2026, 7, 3)  # Friday
    assert clock.date_of(3) == date(2026, 7, 6)  # Monday
    assert clock.date_of(-3) == date(2026, 6, 26)  # Friday before
    assert clock.day_of(date(2026, 7, 4)) == 3  # Saturday rolls to Monday


def test_clock_round_trips() -> None:
    clock = BusinessClock(date(2026, 7, 1))
    for day in range(-120, 121):
        assert clock.day_of(clock.date_of(day)) == day
        assert clock.date_of(day).weekday() < 5


def test_clock_start_on_weekend_rolls_forward() -> None:
    assert BusinessClock(date(2026, 7, 4)).start == date(2026, 7, 6)


def test_apply_is_pure() -> None:
    s0 = seed_state()
    h0 = s0.state_hash()
    s1 = apply(s0, ev(0, "clock.tick", days=2))
    assert s0.state_hash() == h0 and s0.day == 0 and not s0.events
    assert s1.day == 2 and len(s1.events) == 1


def test_fold_is_deterministic() -> None:
    events = [ev(0, "clock.tick"), ev(1, "clock.tick", days=3)]
    assert fold(seed_state(), events).state_hash() == fold(seed_state(), events).state_hash()
    assert fold(seed_state(), events).day == 4


def test_apply_rejects_out_of_order_and_unknown_events() -> None:
    s = seed_state()
    with pytest.raises(ValueError, match="seq"):
        apply(s, ev(1, "clock.tick"))
    with pytest.raises(ValueError, match="no handler"):
        apply(s, ev(0, "nope"))


def test_invoice_received_adds_invoice() -> None:
    s = seed_state()
    inv = s.invoices["INV-1042"].model_dump() | {"id": "INV-9001", "number": "X-1"}
    s1 = apply(s, ev(0, "invoice.received", invoice=inv))
    assert "INV-9001" in s1.invoices and "INV-9001" not in s.invoices
    with pytest.raises(ValueError, match="already exists"):
        apply(s1, ev(1, "invoice.received", invoice=inv))
