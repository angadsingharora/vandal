"""The seams: Tools, Guard (Blue), and FinanceOperator (DESIGN 4, 6)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from pydantic import BaseModel, ConfigDict

from vandal.contracts.controls import Stage
from vandal.contracts.entities import Actor, Case
from vandal.contracts.events import ChannelEvent
from vandal.contracts.verdicts import Verdict

if TYPE_CHECKING:
    from vandal.twin.state import State


class Action(BaseModel):
    """A proposed tool call as the gate sees it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    actor: Actor
    name: str  # tool name, e.g. "payments.submit"
    args: dict[str, Any]


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    verdict: Verdict
    data: dict[str, Any] = {}
    events: list[str] = []  # ids of events this call appended


class Tools(Protocol):
    """The only way to change state; always runs Blue's gate."""

    @property
    def view(self) -> State:
        """Read-only view of the current state. Mutating it is a bug; use call()."""
        ...

    def call(self, actor: Actor, name: str, args: BaseModel) -> ToolResult: ...


class Guard(Protocol):
    """Blue."""

    def check(self, state: State, action: Action, stage: Stage) -> Verdict: ...


class FinanceOperator(Protocol):
    """The Operator."""

    def on_event(self, ev: ChannelEvent, tools: Tools) -> None: ...
    def on_case(self, case: Case, tools: Tools) -> None: ...
