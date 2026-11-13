"""The message hunt over the API (search/message_hunt.py): an attacker model writes fraud
messages, and each runs through the Operator's real intake on a clone. Every attempt streams as
a `log` message on /jobs/{id}/events. The result has a `best` counterexample like a search's, so
/diagnose and /synthesize take a message hunt's id too (they replay it with the rule-based
reader; see the backend README).

Both the attacker and intake call Claude through the record-and-replay cache, so the hunt needs
ANTHROPIC_API_KEY or recordings (DEMO_PLAYBACK=true serves recordings only). Without either,
the job finishes with no attempts and says why."""

from __future__ import annotations

from functools import partial
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from vandal.api import deps
from vandal.sandbox import new_sandbox
from vandal.search.message_hunt import Budget, message_hunt

router = APIRouter()


class MessageHunt(BaseModel):
    attempts: int = Field(default=6, ge=1, le=12)
    max_calls: int = Field(default=24, ge=2, le=48)  # attacker and intake together
    max_tokens: int = Field(default=8000, ge=1000, le=16000)  # per call


@router.post("/runs/{run_id}/hunt-messages")
def start_message_hunt(request: Request, run_id: str, body: MessageHunt) -> dict[str, Any]:
    handle = deps.get_run(request, run_id)
    profile, seed, policy = handle.profile, handle.seed, handle.policy
    factory = partial(new_sandbox, handle.sandbox.profile, policy=policy, use_llm=True)
    budget = Budget(attempts=body.attempts, max_calls=body.max_calls, max_tokens=body.max_tokens)

    def work(job) -> dict[str, Any]:
        result = message_hunt(
            factory,
            seed=seed,
            budget=budget,
            on_attempt=lambda a: job.channel.publish("log", a.model_dump(mode="json")),
        )
        best = result.best
        return {
            **result.model_dump(mode="json"),
            # the shape /diagnose and /synthesize read from a search, inject, or hunt job
            "scenario": best.scenario if best else "a",
            "labels": [],
        }

    meta = {"run": run_id, "profile": profile, "seed": seed, "policy": policy.version}
    return (
        deps.registry(request)
        .submit("message_hunt", work, owner=deps.client(request), **meta, **body.model_dump())
        .summary()
    )
