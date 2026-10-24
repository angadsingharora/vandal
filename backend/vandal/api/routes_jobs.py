"""A0 routes for long work: search (R4), diagnose (R5), verify and metrics (R7), synthesize
(R8). Each long call returns a job; progress streams on /jobs/{id}/events."""

from __future__ import annotations

from functools import partial
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from vandal.api import deps
from vandal.contracts.moves import Move
from vandal.sandbox import new_sandbox
from vandal.search.alphabet import SCENARIOS
from vandal.search.bfs import search
from vandal.synth.cegis import cegis
from vandal.synth.coverage import diagnose
from vandal.synth.propose import LLMProposer, SweepProposer
from vandal.synth.templates import Policy
from vandal.twin.profile import load_profile
from vandal.verify.evidence_pack import Candidate, EvidencePack
from vandal.verify.invariants import Limits
from vandal.verify.replay import replay_detailed
from vandal.verify.suite import collect, scorecard, verify

router = APIRouter()


class SearchRequest(BaseModel):
    policy: str = "v0"
    scenario: str = "a"
    depth: int = Field(default=3, ge=0, le=6)
    workers: int = Field(default=1, ge=1, le=32)
    exhaustive: bool = False
    profile: str = "bayline"
    seed: int = 7


class DiagnoseRequest(BaseModel):
    search_id: str


class SynthesizeRequest(BaseModel):
    search_id: str | None = None  # repair this search's counterexample
    policy: str = "v0"  # otherwise, repair what search finds under this policy
    depth: int = Field(default=3, ge=1, le=6)
    workers: int = Field(default=1, ge=1, le=32)
    max_iterations: int = Field(default=4, ge=1, le=8)
    no_llm: bool = False
    version: str = "v1-synth"
    profile: str = "bayline"
    seed: int = 7


class VerifyRequest(BaseModel):
    policy: str | None = None
    synthesis_id: str | None = None  # verify what this synthesis chose
    parent: str | None = None
    depth: int = Field(default=3, ge=1, le=6)
    workers: int = Field(default=1, ge=1, le=32)
    profile: str = "bayline"
    seed: int = 7


def _factory_for(profile: str):
    return lambda p: partial(new_sandbox, profile, policy=p)


def _done(request: Request, job_id: str, kind: str):
    job = deps.get_job(request, job_id)
    if job.kind != kind:
        raise HTTPException(400, f"{job_id} is a {job.kind} job, not {kind}")
    if job.status != "done":
        raise HTTPException(409, f"{job_id} is {job.status}")
    return job


@router.get("/jobs/{job_id}")
def get_job(request: Request, job_id: str) -> dict[str, Any]:
    job = deps.get_job(request, job_id)
    return {**job.summary(), "result": job.result}


@router.get("/jobs/{job_id}/events")
def job_events(request: Request, job_id: str, start: int | None = None, follow: bool = True):
    """SSE: progress, log entries, and a final `done` or `error`."""
    return deps.sse(request, deps.get_job(request, job_id).channel, start, follow)


@router.post("/search")
def start_search(request: Request, body: SearchRequest) -> dict[str, Any]:
    if body.scenario not in SCENARIOS:
        raise HTTPException(400, f"unknown scenario {body.scenario!r}")
    policy = deps.policy(body.policy)
    reg = deps.registry(request)

    def work(job) -> dict[str, Any]:
        def progress(depth: int, explored: int) -> None:
            job.channel.publish("progress", {"depth": depth, "explored": explored})

        result = search(
            partial(new_sandbox, body.profile, policy=policy),
            SCENARIOS[body.scenario],
            seed=body.seed,
            depth=body.depth,
            workers=body.workers,
            exhaustive=body.exhaustive,
            progress=progress,
        )
        out = result.model_dump(mode="json")
        out |= {"runs_per_second": result.runs_per_second, "ms_per_run": result.ms_per_run}
        if reg.store is not None:
            out["stored_as"] = reg.store.save_search(result, policy=policy.version)
        return out

    return reg.submit("search", work, **body.model_dump()).summary()


@router.post("/diagnose")
def start_diagnose(request: Request, body: DiagnoseRequest) -> dict[str, Any]:
    """Root cause of a finished search's best counterexample (R5)."""
    job = _done(request, body.search_id, "search")
    best = job.result.get("best")
    if best is None:
        return {
            "search_id": body.search_id,
            "diagnosis": None,
            "reason": "the search found no violation",
        }
    meta = job.meta
    factory = partial(new_sandbox, meta["profile"], policy=deps.policy(meta["policy"]))
    moves = [Move.model_validate(m) for m in best["moves"]]
    result, sb, _ = replay_detailed(meta["seed"], moves, sandbox=factory)
    d = diagnose(sb.run.state, result.violations, Limits.from_profile(sb.profile))
    return {"search_id": body.search_id, "diagnosis": d.model_dump(mode="json") if d else None}


@router.post("/synthesize")
def start_synthesize(request: Request, body: SynthesizeRequest) -> dict[str, Any]:
    """CEGIS (R8). Every candidate streams as a `log` message on /jobs/{id}/events."""
    reg = deps.registry(request)
    parent = deps.policy(body.policy)
    start = None
    if body.search_id:
        found = _done(request, body.search_id, "search")
        parent = deps.policy(found.meta["policy"])
        best = found.result.get("best")
        if best is None:
            raise HTTPException(400, f"{body.search_id} found no violation to repair")
        start = [Move.model_validate(m) for m in best["moves"]]
    profile = load_profile(body.profile)

    def work(job) -> dict[str, Any]:
        proposer = SweepProposer(profile) if body.no_llm else LLMProposer(profile)
        result = cegis(
            parent,
            _factory_for(body.profile),
            profile=profile,
            proposer=proposer,
            seed=body.seed,
            depth=body.depth,
            workers=body.workers,
            max_iterations=body.max_iterations,
            version=body.version,
            start=start,
            on_entry=lambda e: job.channel.publish("log", e.model_dump(mode="json")),
        )
        out = result.model_dump(mode="json")
        if reg.store is not None:
            out["stored_as"] = reg.store.save_synthesis(result)
        return out

    return reg.submit("synthesize", work, **body.model_dump()).summary()


@router.post("/verify")
def start_verify(request: Request, body: VerifyRequest) -> dict[str, Any]:
    """The six checks and the evidence pack (R7), for a policy or a synthesis's choice."""
    reg = deps.registry(request)
    candidates = None
    if body.synthesis_id:
        synth = _done(request, body.synthesis_id, "synthesize")
        if synth.result.get("policy") is None:
            raise HTTPException(
                400, f"{body.synthesis_id} didn't produce a policy ({synth.result.get('status')})"
            )
        policy = Policy.model_validate(synth.result["policy"])
        candidates = [
            Candidate(
                source=f"cegis it{e['iteration']} ({e['source']})",
                controls=[*e["base"], e["candidate"]],
                lint=e["lint"],
                result=f"{e['outcome']}: {e['detail']}",
            )
            for e in synth.result["log"]
        ]
    elif body.policy:
        policy = deps.policy(body.policy)
    else:
        raise HTTPException(400, "give a policy or a synthesis_id")
    parent = deps.policy(body.parent or policy.parent or "v0")

    def work(job) -> dict[str, Any]:
        job.channel.publish("progress", {"step": "verifying", "policy": policy.version})
        pack: EvidencePack = verify(
            policy,
            parent,
            _factory_for(body.profile),
            profile=body.profile,
            seed=body.seed,
            depth=body.depth,
            workers=body.workers,
            candidates=candidates,
        )
        for c in pack.checks:
            job.channel.publish("check", c.model_dump(mode="json"))
        if reg.store is not None:
            reg.store.save_evidence_pack(pack, synthesis=body.synthesis_id)
        return pack.model_dump(mode="json")

    return reg.submit(
        "verify", work, **body.model_dump(), policy_json=policy.model_dump(mode="json")
    ).summary()


@router.get("/metrics")
def metrics(
    policies: str = "v0,v1", depth: int = 1, profile: str = "bayline", seed: int = 7
) -> dict[str, Any]:
    """Scorecards side by side (R7). Depth 1 by default so the call stays interactive; the
    evidence pack from /verify has the full-depth numbers."""
    out = {}
    for name in [p.strip() for p in policies.split(",") if p.strip()]:
        policy = deps.policy(name)
        runs = collect(
            policy, partial(new_sandbox, profile, policy=policy), seed=seed, depth=depth, workers=1
        )
        out[name] = scorecard(runs).model_dump(mode="json")
    return {"depth": depth, "scorecards": out}
