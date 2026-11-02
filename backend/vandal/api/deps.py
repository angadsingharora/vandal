"""A0: shared request plumbing for the route modules."""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from vandal.api.registry import Job, Registry, RunHandle
from vandal.api.sse import Channel, stream
from vandal.synth.templates import Policy, available_policies, load_policy
from vandal.twin.profile import builtin_profiles, custom_profiles


def registry(request: Request) -> Registry:
    return request.app.state.registry


def client(request: Request) -> str | None:
    """Who is asking: the `X-Vandal-Client` header (the war room sends a random id it keeps in
    the browser), or `?client=` for a stream. None for a bare curl. Runs belong to the client
    that made them; a reset drops only that client's runs, and `/runs` lists only theirs."""
    raw = request.headers.get("x-vandal-client") or request.query_params.get("client")
    if not raw:
        return None
    raw = raw.strip()[:64]
    return raw or None


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


def policy(name: str | None, request: Request | None = None) -> Policy:
    """A policy by name: one applied through the inbox first, then the built-ins. The API never
    loads an arbitrary path."""
    if request is not None and name in registry(request).applied:
        return registry(request).applied[name]
    if name and name not in available_policies():
        raise HTTPException(400, f"unknown policy {name!r}")
    try:
        return load_policy(name)
    except (FileNotFoundError, ValueError) as err:
        raise HTTPException(400, f"unknown policy {name!r}: {err}") from None


def profile_name(name: str) -> str:
    """A profile the API may seed from: a built-in, or a custom company made in this process.
    A custom one is gone after a restart, so a stale name is a 400 the client can act on, not
    a 500. The API never loads an arbitrary path."""
    if name in custom_profiles() or name in builtin_profiles():
        return name
    raise HTTPException(400, f"unknown profile {name!r}")


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
