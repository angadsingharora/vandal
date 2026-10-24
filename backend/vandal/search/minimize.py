"""R4: delta debugging (ddmin) down to a 1-minimal violating trace.

Given a violating move list and a predicate "this still violates", ddmin removes chunks of
moves, then single moves, until removing any one move makes the violation disappear. Moves keep
their `at`, so timing survives minimization.
"""

from __future__ import annotations

from collections.abc import Callable

from vandal.contracts.moves import Move


def ddmin(moves: list[Move], violates: Callable[[list[Move]], bool]) -> list[Move]:
    if not violates(moves):
        raise ValueError("ddmin needs a violating trace to start from")
    current = list(moves)
    n = 2
    while len(current) >= 2:
        size = max(1, len(current) // n)
        chunks = [current[i : i + size] for i in range(0, len(current), size)]
        reduced = False
        for i, chunk in enumerate(chunks):
            complement = [m for j, c in enumerate(chunks) if j != i for m in c]
            if violates(chunk):
                current, n, reduced = chunk, 2, True
                break
            if violates(complement):
                current, n, reduced = complement, max(n - 1, 2), True
                break
        if not reduced:
            if n >= len(current):
                break
            n = min(len(current), n * 2)
    if len(current) == 1 and violates([]):
        return []
    return current


def same_violation(target: set[str], run: Callable[[list[Move]], set[str]]):
    """Predicate for ddmin: the trace still breaks every invariant in `target`."""

    def violates(moves: list[Move]) -> bool:
        return target <= run(moves)

    return violates


def minimize_trace(moves: list[Move], run: Callable[[list[Move]], set[str]]) -> list[Move]:
    """Shortest sub-trace (1-minimal) that still breaks every invariant the full trace breaks."""
    return ddmin(moves, same_violation(run(moves), run))
