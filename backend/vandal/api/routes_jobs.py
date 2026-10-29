"""A0 routes for long work: search (R4), diagnose (R5), verify and metrics (R7), synthesize
(R8). Each long call returns a job; progress streams on /jobs/{id}/events.

Depth and workers are clamped to the host's limits (api/limits.py). Search, synthesis, and
verification go through the job cache (api/jobcache.py): with playback on, a recorded result
is served at once and its streamed messages replayed; `fresh: true` computes anyway."""

from __future__ import annotations

from functools import partial
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from vandal.api import deps, jobcache
from vandal.api.limits import limits
from vandal.contracts.entities import OracleLabel
from vandal.contracts.moves import Move
from vandal.sandbox import intake_extractor, new_sandbox
from vandal.search.alphabet import SCENARIOS
from vandal.search.bfs import search, search_all
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
    scenario: str = "a"  # a threat family, or "all" for every family in one strike
    depth: int = Field(default=3, ge=0, le=6)
    workers: int | None = Field(default=None, ge=1, le=32)  # None: the host's SEARCH_WORKERS
    exhaustive: bool = False
    fresh: bool = False  # compute even when a recording exists
    profile: str = "bayline"
    seed: int = 7


class DiagnoseRequest(BaseModel):
    search_id: str  # a search job, or an inject job (R9)


class SynthesizeRequest(BaseModel):
    search_id: str | None = None  # repair this search's (or inject's) counterexample
    policy: str = "v0"  # otherwise, repair what search finds under this policy
    depth: int = Field(default=3, ge=1, le=6)
    workers: int | None = Field(default=None, ge=1, le=32)
    max_iterations: int = Field(default=4, ge=1, le=8)
    no_llm: bool = False
    fresh: bool = False
    version: str = "v1-synth"
    profile: str = "bayline"
    seed: int = 7


class VerifyRequest(BaseModel):
    policy: str | None = None
    synthesis_id: str | None = None  # verify what this synthesis chose
    parent: str | None = None
    depth: int = Field(default=3, ge=1, le=6)
    workers: int | None = Field(default=None, ge=1, le=32)
    fresh: bool = False
    profile: str = "bayline"
    seed: int = 7


def _bounded(body: BaseModel) -> dict[str, Any]:
    """The job's meta: the request, with depth and workers as the host allows them."""
    lim = limits()
    meta = body.model_dump()
    if "profile" in meta:
        deps.profile_name(meta["profile"])
    meta["depth"] = lim.depth(meta["depth"])
    meta["workers"] = lim.workers(meta.get("workers"))
    meta["clamped"] = meta["depth"] != body.depth  # type: ignore[attr-defined]
    return meta


def _factory_for(profile: str):
    """Sandbox factories carry the Profile object, not its name: a search's worker processes
    resolve a name against profiles/*.yaml and would never see a custom company (api/
    routes_profiles.py), which lives only in this process."""
    loaded = load_profile(profile)
    return lambda p: partial(new_sandbox, loaded, policy=p)


def _done(request: Request, job_id: str, *kinds: str):
    job = deps.get_job(request, job_id)
    if job.kind not in kinds:
        raise HTTPException(400, f"{job_id} is a {job.kind} job, not {' or '.join(kinds)}")
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


@router.get("/jobs/{job_id}/evidence")
def job_evidence(request: Request, job_id: str) -> JSONResponse:
    """A finished verification's evidence pack as a file to keep."""
    job = _done(request, job_id, "verify")
    name = f"vandal-evidence-{job.result['version']}.json"
    return JSONResponse(
        job.result, headers={"Content-Disposition": f'attachment; filename="{name}"'}
    )


@router.post("/search")
def start_search(request: Request, body: SearchRequest) -> dict[str, Any]:
    if body.scenario != "all" and body.scenario not in SCENARIOS:
        raise HTTPException(400, f"unknown scenario {body.scenario!r}")
    policy = deps.policy(body.policy, request)
    reg = deps.registry(request)
    meta = _bounded(body)
    inputs = {
        "profile": body.profile,
        "seed": body.seed,
        "policy": policy.model_dump(mode="json"),
        "scenario": body.scenario,
        "depth": meta["depth"],
        "exhaustive": body.exhaustive,
    }

    def work(job) -> dict[str, Any]:
        def progress(depth: int, explored: int) -> None:
            job.channel.publish("progress", {"depth": depth, "explored": explored})

        def compute() -> dict[str, Any]:
            factory = partial(new_sandbox, load_profile(body.profile), policy=policy)
            options = dict(
                seed=body.seed,
                depth=meta["depth"],
                workers=meta["workers"],
                exhaustive=body.exhaustive,
                progress=progress,
            )
            if body.scenario == "all":
                result = search_all(factory, **options)
            else:
                result = search(factory, SCENARIOS[body.scenario], **options)
            out = result.model_dump(mode="json")
            out |= {"runs_per_second": result.runs_per_second, "ms_per_run": result.ms_per_run}
            if reg.store is not None:
                out["stored_as"] = reg.store.save_search(result, policy=policy.version)
            return out

        def on_hit(recorded: dict[str, Any]) -> None:
            progress(recorded["depth"], recorded["explored"])

        return jobcache.serve("search", inputs, compute, fresh=body.fresh, on_hit=on_hit)

    return reg.submit("search", work, **meta).summary()


@router.post("/diagnose")
def start_diagnose(request: Request, body: DiagnoseRequest) -> dict[str, Any]:
    """Root cause of a finished search's best counterexample (R5)."""
    job = _done(request, body.search_id, "search", "inject", "hunt")
    best = job.result.get("best")
    if best is None:
        return {
            "search_id": body.search_id,
            "diagnosis": None,
            "reason": "the search found no violation",
        }
    meta = job.meta
    factory = partial(
        new_sandbox, load_profile(meta["profile"]), policy=deps.policy(meta["policy"], request)
    )
    moves = [Move.model_validate(m) for m in best["moves"]]
    labels = [OracleLabel.model_validate(lb) for lb in job.result.get("labels", [])]
    result, sb, _ = replay_detailed(meta["seed"], moves, sandbox=factory, labels=labels)
    d = diagnose(sb.run.state, result.violations, Limits.from_profile(sb.profile))
    return {"search_id": body.search_id, "diagnosis": d.model_dump(mode="json") if d else None}


@router.post("/synthesize")
def start_synthesize(request: Request, body: SynthesizeRequest) -> dict[str, Any]:
    """CEGIS (R8). Every candidate streams as a `log` message on /jobs/{id}/events."""
    reg = deps.registry(request)
    parent = deps.policy(body.policy, request)
    start, labels, scenario = None, [], "a"
    if body.search_id:
        found = _done(request, body.search_id, "search", "inject", "hunt")
        parent = deps.policy(found.meta["policy"], request)
        best = found.result.get("best")
        if best is None:
            raise HTTPException(400, f"{body.search_id} found no violation to repair")
        start = [Move.model_validate(m) for m in best["moves"]]
        labels = [OracleLabel.model_validate(lb) for lb in found.result.get("labels", [])]
        scenario = found.result.get("scenario") or found.meta.get("scenario") or "a"
    profile = load_profile(body.profile)
    meta = _bounded(body)
    inputs = {
        "profile": body.profile,
        "seed": body.seed,
        "parent": parent.model_dump(mode="json"),
        "start": [m.model_dump(mode="json") for m in start] if start else None,
        "labels": [lb.model_dump(mode="json") for lb in labels],
        "scenario": scenario,
        "depth": meta["depth"],
        "max_iterations": body.max_iterations,
        "no_llm": body.no_llm,
        "version": body.version,
    }

    def work(job) -> dict[str, Any]:
        def compute() -> dict[str, Any]:
            proposer = SweepProposer(profile) if body.no_llm else LLMProposer(profile)
            result = cegis(
                parent,
                _factory_for(body.profile),
                profile=profile,
                proposer=proposer,
                seed=body.seed,
                depth=meta["depth"],
                workers=meta["workers"],
                max_iterations=body.max_iterations,
                version=body.version,
                start=start,
                start_labels=labels,
                scenario=scenario,
                on_entry=lambda e: job.channel.publish("log", e.model_dump(mode="json")),
            )
            out = result.model_dump(mode="json")
            if reg.store is not None:
                out["stored_as"] = reg.store.save_synthesis(result)
            return out

        def on_hit(recorded: dict[str, Any]) -> None:
            for entry in recorded.get("log", []):
                job.channel.publish("log", entry)

        return jobcache.serve("synthesize", inputs, compute, fresh=body.fresh, on_hit=on_hit)

    return reg.submit("synthesize", work, **meta).summary()


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
        policy = deps.policy(body.policy, request)
    else:
        raise HTTPException(400, "give a policy or a synthesis_id")
    parent = deps.policy(body.parent or policy.parent or "v0", request)
    meta = _bounded(body)
    inputs = {
        "profile": body.profile,
        "seed": body.seed,
        "policy": policy.model_dump(mode="json"),
        "parent": parent.model_dump(mode="json"),
        "depth": meta["depth"],
        "candidates": [c.model_dump(mode="json") for c in candidates] if candidates else None,
    }

    def work(job) -> dict[str, Any]:
        job.channel.publish("progress", {"step": "verifying", "policy": policy.version})

        def compute() -> dict[str, Any]:
            pack: EvidencePack = verify(
                policy,
                parent,
                _factory_for(body.profile),
                profile=body.profile,
                seed=body.seed,
                depth=meta["depth"],
                workers=meta["workers"],
                candidates=candidates,
                intake=intake_extractor(body.profile),
            )
            for c in pack.checks:
                job.channel.publish("check", c.model_dump(mode="json"))
            if reg.store is not None:
                reg.store.save_evidence_pack(pack, synthesis=body.synthesis_id)
            return pack.model_dump(mode="json")

        def on_hit(recorded: dict[str, Any]) -> None:
            for check in recorded.get("checks", []):
                job.channel.publish("check", check)

        return jobcache.serve("verify", inputs, compute, fresh=body.fresh, on_hit=on_hit)

    return reg.submit("verify", work, **meta, policy_json=policy.model_dump(mode="json")).summary()


@router.get("/metrics")
def metrics(
    request: Request,
    policies: str = "v0,v1",
    depth: int = 1,
    profile: str = "bayline",
    seed: int = 7,
) -> dict[str, Any]:
    """Scorecards side by side (R7). Depth 1 by default so the call stays interactive; the
    evidence pack from /verify has the full-depth numbers."""
    deps.profile_name(profile)
    depth = limits().depth(depth)
    out = {}
    for name in [p.strip() for p in policies.split(",") if p.strip()]:
        policy = deps.policy(name, request)
        runs = collect(
            policy,
            partial(new_sandbox, load_profile(profile), policy=policy),
            seed=seed,
            depth=depth,
            workers=1,
            intake=intake_extractor(profile),
        )
        out[name] = scorecard(runs).model_dump(mode="json")
    return {"depth": depth, "scorecards": out}
