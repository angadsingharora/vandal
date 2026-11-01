"""R9 over the API: a user-authored threat, in plain language or as composed moves, run against a
run's company and policy (DESIGN 8.4). The same steps as `vandal inject`: read the threat into a
plan, run it on a fresh clone, search k moves around it if it doesn't break anything by itself,
and minimize what breaks. The job's result has a `best` counterexample like a search's, so
/diagnose and /synthesize take an inject job's id too."""

from __future__ import annotations

from functools import partial
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from vandal.api import deps
from vandal.contracts.entities import OracleLabel
from vandal.contracts.moves import Move
from vandal.sandbox import new_sandbox
from vandal.search import red
from vandal.search.alphabet import SCENARIOS
from vandal.search.bfs import search
from vandal.search.minimize import minimize_trace
from vandal.verify.replay import replay

router = APIRouter()


class Inject(BaseModel):
    description: str | None = None  # plain language
    moves: list[Move] | None = None  # compose: raw moves (wins over the description)
    labels: list[OracleLabel] = []  # a composed trace's answer key
    scenario: str | None = None  # search window to seed around it
    depth: int = Field(default=2, ge=0, le=4)
    workers: int = Field(default=1, ge=1, le=32)
    no_llm: bool = False
    dry_run: bool = False  # only read the threat into a plan


@router.post("/runs/{run_id}/inject")
def inject(request: Request, run_id: str, body: Inject) -> dict[str, Any]:
    handle = deps.get_run(request, run_id)
    profile, seed, policy = handle.profile, handle.seed, handle.policy
    factory = partial(new_sandbox, handle.sandbox.profile, policy=policy)  # the object: see jobs
    if body.scenario is not None and body.scenario not in SCENARIOS:
        raise HTTPException(400, f"unknown scenario {body.scenario!r}")
    if body.moves:
        plan = red.ThreatPlan(
            description=body.description or "composed trace",
            moves=body.moves,
            labels=body.labels,
            scenario=body.scenario or "a",
            source="trace",
        )
    elif body.description and body.description.strip():
        try:
            plan = red.plan(body.description, factory, seed, use_llm=not body.no_llm)
        except ValueError as err:
            raise HTTPException(400, str(err)) from None
        if body.scenario:
            plan.scenario = body.scenario
    else:
        raise HTTPException(400, "give a description or moves")
    if body.dry_run:
        return {"plan": plan.model_dump(mode="json")}

    def work(job) -> dict[str, Any]:
        def violated(moves) -> set[str]:
            return set(replay(seed, moves, sandbox=factory, labels=plan.labels).violated)

        fresh = replay(seed, plan.moves, sandbox=factory, labels=plan.labels)
        job.channel.publish("progress", {"step": "fresh clone", "violated": fresh.violated})
        explored, needed = 0, True
        if fresh.violations:
            moves = minimize_trace(plan.moves, violated)
        else:

            def progress(depth: int, n: int) -> None:
                job.channel.publish("progress", {"depth": depth, "explored": n})

            found = search(
                factory,
                SCENARIOS[plan.scenario],
                seed=seed,
                depth=body.depth,
                workers=body.workers,
                around=plan.moves,
                labels=plan.labels,
                progress=progress,
            )
            explored = found.explored
            moves = minimize_trace(found.best.moves, violated) if found.best else None
            needed = bool(moves) and any(m in moves for m in plan.moves)
        best = None
        if moves:
            final = replay(seed, moves, sandbox=factory, labels=plan.labels)
            best = {
                "moves": [m.model_dump() for m in moves],
                "violated": final.violated,
                "exposure": final.exposure,
            }
        return {
            "plan": plan.model_dump(mode="json"),
            "scenario": plan.scenario,
            "fresh": {**fresh.model_dump(mode="json"), "violated": fresh.violated},
            "explored": explored,
            "best": best,
            "needed": needed,  # did the counterexample use the injected moves?
            "labels": [lb.model_dump(mode="json") for lb in plan.labels],
        }

    meta = {"run": run_id, "profile": profile, "seed": seed, "policy": policy.version}
    return (
        deps.registry(request)
        .submit("inject", work, owner=deps.client(request), **meta, depth=body.depth)
        .summary()
    )
