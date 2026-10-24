"""Benchmark the twin's hot paths for search (IMPLEMENTATION R4 budget: ~5 ms per run).

Run: uv run python scripts/bench_twin.py
"""

from __future__ import annotations

import time
from collections.abc import Callable

from vandal.contracts.events import Event
from vandal.twin.reducer import apply, fold
from vandal.twin.seed import seed_state
from vandal.twin.state import State

RUN_EVENTS = 30


def _ms(fn: Callable[[], object], n: int) -> float:
    start = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - start) / n * 1000


def _events(state: State, n: int) -> list[Event]:
    base = len(state.events)
    return [
        Event(id=f"EV-B{i}", seq=base + i, day=0, kind="clock.tick", actor="system")
        for i in range(n)
    ]


def main() -> None:
    seed = seed_state()
    events = _events(seed, RUN_EVENTS)

    def apply_each() -> None:
        s = seed
        for ev in events:
            s = apply(s, ev)

    rows = {
        "clone": _ms(seed.clone, 200),
        "state_hash": _ms(seed.state_hash, 200),
        f"run: apply() x{RUN_EVENTS} (pure)": _ms(apply_each, 10),
        f"run: fold() x{RUN_EVENTS}": _ms(lambda: fold(seed, events), 50),
    }
    if hasattr(seed, "entity_hash"):
        warm = seed.clone()
        warm.entity_hash()
        rows["entity_hash (cold)"] = _ms(lambda: seed.clone().entity_hash(), 50)
        rows["entity_hash (warm)"] = _ms(warm.entity_hash, 200)
    for name, ms in rows.items():
        print(f"{name:<32} {ms:8.3f} ms")


if __name__ == "__main__":
    main()
