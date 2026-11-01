"""The hunt over the API: attacks from outside the preset threat families, drawn from a written
playbook and tested in the twin (search/hunt.py), with a pause before each attempt for the
audience. Every attempt streams as a `log` message on /jobs/{id}/events. The result has a `best`
counterexample like a search's, so /diagnose and /synthesize take a hunt job's id too. No model
is involved, so the hunt runs with or without an API key."""

from __future__ import annotations

from functools import partial
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from vandal.api import deps
from vandal.sandbox import new_sandbox
from vandal.search.hunt import hunt, window_for

router = APIRouter()


class Hunt(BaseModel):
    attempts: int = Field(default=6, ge=1, le=12)
    keep_going: bool = False  # keep hunting after the first hit


@router.post("/runs/{run_id}/hunt")
def start_hunt(request: Request, run_id: str, body: Hunt) -> dict[str, Any]:
    handle = deps.get_run(request, run_id)
    profile, seed, policy = handle.profile, handle.seed, handle.policy
    factory = partial(new_sandbox, handle.sandbox.profile, policy=policy)  # the object: see jobs

    def work(job) -> dict[str, Any]:
        result = hunt(
            factory,
            seed=seed,
            attempts=body.attempts,
            keep_going=body.keep_going,
            on_attempt=lambda a: job.channel.publish("log", a.model_dump(mode="json")),
        )
        best = result.best
        return {
            **result.model_dump(mode="json"),
            # the shape /diagnose and /synthesize read from a search or inject job
            "best": best.model_dump(mode="json") if best else None,
            "scenario": window_for(best.moves) if best else "a",
            "labels": best.model_dump(mode="json")["labels"] if best else [],
        }

    meta = {"run": run_id, "profile": profile, "seed": seed, "policy": policy.version}
    return (
        deps.registry(request)
        .submit("hunt", work, owner=deps.client(request), **meta, **body.model_dump())
        .summary()
    )
