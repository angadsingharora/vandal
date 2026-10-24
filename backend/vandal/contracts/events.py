"""Events: the append-only log. A run is fold(seed, events) (DESIGN 5.4)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from vandal.contracts.entities import SimDay


class Event(BaseModel):
    """One state-changing fact. Never updated; corrections reference what they correct (INV-8)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str  # EV-000123
    seq: int
    day: SimDay
    kind: str  # e.g. "invoice.received", "gate.verdict", "bank.ack"
    actor: str
    payload: dict[str, Any] = {}
    caused_by: list[str] = []  # event ids: the chain the coverage analysis and explain walk
    corrects: str | None = None


class ChannelEvent(BaseModel):
    """Something arriving on a channel that the Operator must interpret (intake)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    day: SimDay
    channel: Literal["email", "portal", "agent_msg", "phone_in", "video", "bank_feed", "system"]
    sender: str
    subject: str = ""
    body: str = ""
    attachments: list[str] = []
    meta: dict[str, Any] = {}
