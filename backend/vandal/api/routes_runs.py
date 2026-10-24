"""A0 routes for runs: create, operate, read state, stream events, replay (R1, R2, R3, R5)."""

from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from vandal.api import deps
from vandal.api.registry import RunHandle
from vandal.contracts.entities import OracleLabel
from vandal.contracts.moves import Move
from vandal.synth.coverage import build_chain
from vandal.twin.world import run_step, schedule
from vandal.verify.invariants import Limits, check
from vandal.verify.replay import replay_detailed

router = APIRouter()


class NewRun(BaseModel):
    profile: str = "bayline"
    seed: int = 7
    policy: str = "v0"


class Operate(BaseModel):
    days: int = Field(default=5, ge=1, le=90)


class Replay(BaseModel):
    moves: list[Move]
    labels: list[OracleLabel] = []
    days: int = Field(default=2, ge=1, le=30)
    profile: str = "bayline"
    seed: int = 7
    policy: str = "v0"


def summary(handle: RunHandle) -> dict[str, Any]:
    with handle.lock:
        state = handle.state
        violations = check(state, None, Limits.from_profile(handle.sandbox.profile))
        return {
            "run_id": handle.id,
            "company": state.company,
            "profile": handle.profile,
            "seed": handle.seed,
            "policy": handle.policy.version,
            "day": state.day,
            "invoices": dict(Counter(i.status for i in state.invoices.values())),
            "payments": dict(Counter(p.status for p in state.payments.values())),
            "bank": {
                b.id: {"name": b.name, "balance": b.balance} for b in state.bank_accounts.values()
            },
            "open_approvals": sum(
                1 for r in state.approval_requests.values() if r.status == "pending"
            ),
            "change_requests": dict(Counter(c.status for c in state.change_requests.values())),
            "violations": [v.model_dump() for v in violations],
            "events": len(state.events),
            "state_hash": state.state_hash(),
        }


def _create(request: Request, body: NewRun) -> dict[str, Any]:
    handle = deps.registry(request).create_run(body.profile, body.seed, deps.policy(body.policy))
    return summary(handle)


@router.post("/demo/reset")
def demo_reset(request: Request, body: NewRun | None = None) -> dict[str, Any]:
    """Drop every run and start one fresh company."""
    deps.registry(request).reset()
    return _create(request, body or NewRun())


@router.post("/runs")
def create_run(request: Request, body: NewRun | None = None) -> dict[str, Any]:
    return _create(request, body or NewRun())


@router.get("/runs")
def list_runs(request: Request) -> list[dict[str, Any]]:
    return [
        {
            "run_id": h.id,
            "policy": h.policy.version,
            "day": h.state.day,
            "events": len(h.state.events),
        }
        for h in deps.registry(request).runs.values()
    ]


@router.get("/runs/{run_id}/state")
def run_state(request: Request, run_id: str) -> dict[str, Any]:
    return summary(deps.get_run(request, run_id))


@router.get("/runs/{run_id}/ledger")
def run_ledger(request: Request, run_id: str) -> list[dict[str, Any]]:
    handle = deps.get_run(request, run_id)
    with handle.lock:
        return [je.model_dump(mode="json") for je in handle.state.journal]


@router.get("/runs/{run_id}/events")
def run_events(request: Request, run_id: str, start: int | None = None, follow: bool = True):
    """SSE: every event of the run from `start`, then live (`event: event` messages)."""
    return deps.sse(request, deps.get_run(request, run_id).channel, start, follow)


@router.post("/runs/{run_id}/operate")
def operate(request: Request, run_id: str, body: Operate | None = None) -> dict[str, Any]:
    """Run the World for `days` business days on a worker thread. Events stream on
    /runs/{id}/events; day-by-day progress on /jobs/{job}/events."""
    handle = deps.get_run(request, run_id)
    days = (body or Operate()).days

    def work(job) -> dict[str, Any]:
        sb = handle.sandbox
        with handle.lock:
            start = sb.run.state.day
            for step in schedule(days, start_day=start):
                run_step(sb.run, sb.tools, step, sb.operator, sb.approver)
                if step.kind == "tick":
                    job.channel.publish(
                        "progress", {"day": step.day + 1, "events": len(sb.run.state.events)}
                    )
            if handle.writer is not None:
                handle.writer.flush()
        return summary(handle)

    return deps.registry(request).submit("operate", work, run_id=run_id, days=days).summary()


@router.get("/runs/{run_id}/chain/{payment}")
def chain(request: Request, run_id: str, payment: str) -> dict[str, Any]:
    """The authorization chain for one payment (R5)."""
    handle = deps.get_run(request, run_id)
    with handle.lock:
        if payment not in handle.state.payments:
            raise HTTPException(404, f"no payment {payment} in {run_id}")
        return build_chain(
            handle.state, payment, Limits.from_profile(handle.sandbox.profile)
        ).model_dump(mode="json")


@router.post("/replay")
def replay(request: Request, body: Replay) -> dict[str, Any]:
    """Replay a trace on a fresh company as a new run; its events stream like any run's."""
    reg = deps.registry(request)
    handle = reg.create_run(body.profile, body.seed, deps.policy(body.policy), kind="replay")
    with handle.lock:
        result, _, _ = replay_detailed(
            body.seed,
            body.moves,
            sandbox=lambda _seed: handle.sandbox,
            days=body.days,
            labels=body.labels,
        )
        if handle.writer is not None:
            handle.writer.flush()
    return {
        "run": summary(handle),
        "result": {**result.model_dump(mode="json"), "violated": result.violated},
    }
