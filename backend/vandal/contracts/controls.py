"""Checks (what the gate runs) and Controls (what synthesis produces) (DESIGN 9.2)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

Stage = Literal[
    "intake",
    "invoice.match",
    "pre_approve",
    "change_request",
    "verification",
    "schedule",
    "pre_execute",
    "submit",
    "retry",
    "refund",
    "journal",
    "recovery",
    "message.outbound",
]

Decision = Literal["allow", "hold", "escalate", "block"]

# Most restrictive wins when several checks match (DESIGN 7: block > hold > escalate > allow).
# A hold outranks an escalation: a human approval must never clear a hold that needs evidence,
# e.g. a $40k payment to an unverified account that trips both T1 and the approval threshold.
DECISION_ORDER: dict[str, int] = {"allow": 0, "escalate": 1, "hold": 2, "block": 3}


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fact: str  # name of a deterministic fact, e.g. "payee_account.status"
    op: Literal["eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in", "changed_since"]
    value: Any = None


class Predicate(BaseModel):
    """A conjunction of conditions over deterministic facts. Empty means always true."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    all: list[Condition] = []


class Requirement(BaseModel):
    """Evidence that clears a hold. The gate clears only when a matching evidence event exists."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    accepted_channels: list[str]
    contact_as_of: Literal["current", "before_request"] | None = None
    window_days: int | None = None


class Check(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    stage: Stage
    when: Predicate
    action: Decision
    require: Requirement | None = None


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    template: Literal["T1", "T2", "T3", "T4", "T5", "T6"]
    params: dict[str, str | int | list[str]]

    def compile(self) -> list[Check]:
        # The templates live in synth/; imported here lazily so contracts stay a leaf.
        from vandal.synth.templates import compile_control

        return compile_control(self)
