"""Verdicts: what the gate returns for every tool call."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from vandal.contracts.controls import Decision


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: Decision
    fired: list[str]  # check ids
    facts: dict[str, Any]  # the facts evaluated (the evidence)
    cites: list[str]  # event, approval, and evidence ids
