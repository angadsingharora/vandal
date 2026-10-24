"""A0: shared request plumbing for the route modules."""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from vandal.api.registry import Job, Registry, RunHandle
from vandal.api.sse import Channel, stream
from vandal.synth.templates import Policy, available_policies, load_policy


def registry(request: Request) -> Registry:
    return request.app.state.registry


def get_run(request: Request, run_id: str) -> RunHandle:
    try:
        return registry(request).run(run_id)
    except KeyError:
        raise HTTPException(404, f"no run {run_id}") from None


def get_job(request: Request, job_id: str) -> Job:
    try:
        return registry(request).job(job_id)
    except KeyError:
        raise HTTPException(404, f"no job {job_id}") from None


def policy(name: str | None) -> Policy:
    """A policy by name only; the API never loads an arbitrary path."""
    if name and name not in available_policies():
        raise HTTPException(400, f"unknown policy {name!r}")
    try:
        return load_policy(name)
    except (FileNotFoundError, ValueError) as err:
        raise HTTPException(400, f"unknown policy {name!r}: {err}") from None


def sse(request: Request, channel: Channel, start: int | None, follow: bool) -> StreamingResponse:
    """`start` from the query, else the Last-Event-ID header (resume after it), else 0."""
    if start is None:
        last = request.headers.get("last-event-id")
        start = int(last) + 1 if last and last.isdigit() else 0
    return StreamingResponse(
        stream(channel, start, follow),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
