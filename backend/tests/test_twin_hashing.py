"""Search-facing twin semantics: in-place fold, entity-only hash for dedup, digest caching."""

from __future__ import annotations

import pytest

from vandal.contracts.entities import Invoice
from vandal.contracts.events import Event
from vandal.twin.reducer import apply, apply_in_place, fold
from vandal.twin.seed import seed_state


def _tick(seq: int, days: int = 1) -> Event:
    return Event(
        id=f"EV-T{seq}", seq=seq, day=0, kind="clock.tick", actor="system", payload={"days": days}
    )


@pytest.fixture(scope="module")
def seed():
    return seed_state()


def test_fold_matches_step_by_step_apply(seed) -> None:
    events = [_tick(i) for i in range(5)]
    stepped = seed
    for ev in events:
        stepped = apply(stepped, ev)
    assert fold(seed, events).state_hash() == stepped.state_hash()


def test_fold_does_not_touch_its_input(seed) -> None:
    before = seed.state_hash()
    fold(seed, [_tick(i) for i in range(3)])
    assert seed.state_hash() == before and not seed.events


def test_entity_hash_ignores_the_event_log(seed) -> None:
    # Same company state reached by two different histories: search must treat them as one.
    one_step = fold(seed, [_tick(0, days=2)])
    two_steps = fold(seed, [_tick(0), _tick(1)])
    assert one_step.entity_hash() == two_steps.entity_hash()
    assert one_step.state_hash() != two_steps.state_hash()


def test_entity_hash_ignores_insertion_order(seed) -> None:
    a = Invoice(
        id="INV-X1",
        vendor="V-001",
        number="X1",
        amount=100,
        dimension="P-01",
        received_on=0,
        due_date=10,
    )
    b = Invoice(
        id="INV-X2",
        vendor="V-001",
        number="X2",
        amount=200,
        dimension="P-01",
        received_on=0,
        due_date=10,
    )
    s1, s2 = seed.clone(), seed.clone()
    s1.put("invoices", a)
    s1.put("invoices", b)
    s2.put("invoices", b)
    s2.put("invoices", a)
    assert s1.entity_hash() == s2.entity_hash()


def test_update_invalidates_the_cached_digest(seed) -> None:
    state = seed.clone()
    original = state.entity_hash()
    state.update("vendors", "V-007", status="blocked")
    changed = state.entity_hash()
    state.update("vendors", "V-007", status="active")
    assert changed != original
    assert state.entity_hash() == original


def test_update_on_a_clone_leaves_the_source_alone(seed) -> None:
    clone = seed.clone()
    clone.update("vendors", "V-007", status="blocked")
    assert seed.vendors["V-007"].status == "active"
    assert seed.entity_hash() != clone.entity_hash()


def test_apply_in_place_checks_sequence(seed) -> None:
    state = seed.clone()
    apply_in_place(state, _tick(0))
    with pytest.raises(ValueError):
        apply_in_place(state, _tick(5))
