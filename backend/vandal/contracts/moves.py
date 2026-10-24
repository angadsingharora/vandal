"""Moves: one adversary or environment step, discretized so search can enumerate it (DESIGN 8.1)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

MoveKind = Literal[
    "change_request",
    "inbound_confirmation",
    "submit_invoice",
    "fault",
    "trigger_batch",
    "retry",
    "deposit",
    "refund_request",
    "tick",
    "message",  # content with no structured request: an inquiry, pressure, small talk
]


class Move(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: MoveKind
    params: dict[str, str | int]
    at: int  # insertion point in the World schedule (timing)
