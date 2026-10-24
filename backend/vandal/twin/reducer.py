"""R1: apply(state, event) -> state, a pure function.

Each event kind has one handler. Handlers mutate a clone, never the input, so callers can keep
any earlier state. Later slices register their own kinds (flows in R2, bank in R2, ...).
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


def apply(state: State, event: Event) -> State:
    if event.seq != len(state.events):
        raise ValueError(f"event {event.id} has seq {event.seq}, expected {len(state.events)}")
    handler = HANDLERS.get(event.kind)
    if handler is None:
        raise ValueError(f"no handler for event kind {event.kind!r}")
    nxt = state.clone()
    handler(nxt, event)
    nxt.events.append(event)
    return nxt


def fold(state: State, events: Iterable[Event]) -> State:
    for event in events:
        state = apply(state, event)
    return state


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
    state.invoices[invoice.id] = invoice
