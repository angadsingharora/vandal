"""R2: the deterministic World schedule of legitimate events over N business days.

Each business day runs the same steps in order:

  ops        the Operator validates invoices, requests approvals, schedules approved ones
  approvals  the approver works the inbox
  batch      the Operator's payment run: execute and submit scheduled payments
  bank       the bank settles T+1, then the Operator reconciles the feed
  tick       the clock advances one business day

Search (R4) inserts adversary moves between these steps; a move's `at` is a step index.
Operators are passed in, never imported, so the twin stays independent of any one agent.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

from vandal.contracts.events import ChannelEvent, Event
from vandal.contracts.interfaces import FinanceOperator, Tools
from vandal.twin import bank
from vandal.twin.reducer import apply_in_place
from vandal.twin.state import State

StepKind = Literal["ops", "approvals", "batch", "bank", "tick"]
DAY_STEPS: tuple[StepKind, ...] = ("ops", "approvals", "batch", "bank", "tick")


class Run:
    """Owns one run's state and its append-only event log."""

    def __init__(self, state: State) -> None:
        self.state = state.clone()

    def emit(
        self,
        kind: str,
        payload: dict[str, Any],
        actor: str = "system",
        caused_by: Iterable[str] = (),
    ) -> Event:
        seq = len(self.state.events)
        event = Event(
            id=f"EV-{seq:06d}",
            seq=seq,
            day=self.state.day,
            kind=kind,
            actor=actor,
            payload=payload,
            caused_by=list(caused_by),
        )
        apply_in_place(self.state, event)
        return event


@dataclass(frozen=True)
class Step:
    index: int
    day: int
    kind: StepKind


def schedule(days: int, start_day: int = 0) -> list[Step]:
    steps: list[Step] = []
    for day in range(start_day, start_day + days):
        for kind in DAY_STEPS:
            steps.append(Step(len(steps), day, kind))
    return steps


def _signal(step: Step, channel: str, subject: str) -> ChannelEvent:
    return ChannelEvent(
        id=f"CH-{step.index:05d}",
        day=step.day,
        channel=channel,
        sender="scheduler",
        subject=subject,
    )


def run_step(
    run: Run, tools: Tools, step: Step, operator: FinanceOperator, approver: FinanceOperator
) -> None:
    match step.kind:
        case "ops":
            operator.on_event(_signal(step, "system", "daily_ops"), tools)
        case "approvals":
            approver.on_event(_signal(step, "system", "approvals_inbox"), tools)
        case "batch":
            operator.on_event(_signal(step, "system", "payment_batch"), tools)
        case "bank":
            for kind, payload in bank.settle_due(run.state):
                run.emit(kind, payload, actor="bank")
            operator.on_event(_signal(step, "bank_feed", "bank_feed"), tools)
        case "tick":
            run.emit("clock.tick", {"days": 1})


def run_world(
    run: Run, tools: Tools, operator: FinanceOperator, approver: FinanceOperator, days: int
) -> Run:
    for step in schedule(days, start_day=run.state.day):
        run_step(run, tools, step, operator, approver)
    return run
