"""R1: State, clone(), state_hash(). R0 only fixes the type so contracts can reference it."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class State(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: int = 0
