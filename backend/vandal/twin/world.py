"""R2: the deterministic World schedule of legitimate events over N business days.

Each business day runs the same steps in order:

  ops        the Operator validates invoices, requests approvals, schedules approved ones
  approvals  the approver works the inbox
  batch      the Operator's payment run: execute and submit scheduled payments
  bank       the bank settles T+1, then the Operator reconciles the feed
  tick       the clock advances one business day

Search (R4) inserts adversary moves between these steps; a move's `at` is a step index.
Operators are passed in, never imported, so the twin stays independent of any one agent. So is
the Environment (twin/evidence.py), which answers callbacks; Tools never see it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal

from vandal.contracts.events import ChannelEvent, Event
from vandal.contracts.interfaces import FinanceOperator, Tools
from vandal.twin import bank
from vandal.twin.evidence import Environment, LegitEnvironment, answer_callbacks, answered_notice
from vandal.twin.reducer import apply_in_place
from vandal.twin.state import State, construct

StepKind = Literal["ops", "approvals", "batch", "bank", "tick"]
DAY_STEPS: tuple[StepKind, ...] = ("ops", "approvals", "batch", "bank", "tick")


class Run:
    """Owns one run's state and its append-only event log."""

    def __init__(
        self,
        state: State,
        sink: Callable[[Event], None] | None = None,
        monitor: Callable[[Run, Step], None] | None = None,
    ) -> None:
        """`sink` sees every event after it's applied (persistence, R12; live streams, A0).
        `monitor` runs after every World step (Blue's runtime checks, B2)."""
        self.state = state.clone()
        self.sink = sink
        self.monitor = monitor

    def emit(
        self,
        kind: str,
        payload: dict[str, Any],
        actor: str = "system",
        caused_by: Iterable[str] = (),
    ) -> Event:
        seq = len(self.state.events)
        event = construct(  # the hot path: every field is built here, so skip validation
            Event,
            {
                "id": f"EV-{seq:06d}",
                "seq": seq,
                "day": self.state.day,
                "kind": kind,
                "actor": actor,
                "payload": payload,
                "caused_by": list(caused_by),
                "corrects": None,
            },
        )
        apply_in_place(self.state, event)
        if self.sink is not None:
            self.sink(event)
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


def _alert_notice(step: Step, alert: dict[str, Any]) -> ChannelEvent:
    """What the Operator hears when Blue's runtime monitor raises an alert."""
    return ChannelEvent(
        id=f"ALERT-{step.index:05d}-{alert['invariant']}-{alert['subject']}",
        day=step.day,
        channel="system",
        sender="blue",
        subject="guard_alert",
        meta={"intent": "guard_alert", **alert},
    )


def _signal(step: Step, channel: str, subject: str) -> ChannelEvent:
    return ChannelEvent(
        id=f"CH-{step.index:05d}",
        day=step.day,
        channel=channel,
        sender="scheduler",
        subject=subject,
    )


def settle(
    run: Run, tools: Tools, operator: FinanceOperator, env: Environment | None, rounds: int = 8
) -> None:
    """Let the environment answer what the Operator just set in motion (outbound callbacks),
    and tell the Operator, until nothing is pending. Synchronous, like a phone call."""
    env = env or LegitEnvironment()
    for _ in range(rounds):
        answers = answer_callbacks(run.state, env)
        if not answers:
            return
        for kind, payload in answers:
            run.emit(kind, payload, actor="phone")
        for _kind, payload in answers:
            evidence = run.state.evidence[payload["evidence"]]
            operator.on_event(answered_notice(evidence, run.state.day), tools)


def run_step(
    run: Run,
    tools: Tools,
    step: Step,
    operator: FinanceOperator,
    approver: FinanceOperator,
    env: Environment | None = None,
) -> None:
    if step.kind == "ops":
        # Open cases come up first thing each business day (O2).
        for case in [c for c in run.state.cases.values() if c.status == "open"]:
            operator.on_case(case, tools)
    _run_step(run, tools, step, operator, approver)
    settle(run, tools, operator, env)
    if run.monitor is not None:
        for alert in run.monitor(run, step) or []:
            operator.on_event(_alert_notice(step, alert), tools)
        settle(run, tools, operator, env)


def _run_step(
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
            for kind, payload in bank.answer_recalls(run.state):
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
