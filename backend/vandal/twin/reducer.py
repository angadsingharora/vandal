"""R1: apply(state, event) -> state, a pure function, plus the in-place path search uses.

Each event kind has one handler. A handler changes the state it's given through
State.put()/update() only, never by editing an entity. apply() hands it a fresh clone, so callers
keep every earlier state; fold() clones once per run and then applies in place. Later slices
register their own kinds (flows in R2, bank in R2, ...).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from vandal.contracts.entities import Invoice
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
