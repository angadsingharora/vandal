"""A0: the FastAPI app.

    uv run uvicorn vandal.api.main:app --reload

Runs live in memory (api/registry.py). With DATABASE_URL set, every run's events and every
search, synthesis, and evidence pack are also persisted (api/db.py, R12). The war-room frontend
reads state over JSON and follows runs and jobs over SSE.

`/settings` holds the demo switches the war room flips: LLM playback (DEMO_PLAYBACK, read by
vandal/llm.py and vandal/api/jobcache.py) for this server process, and reports the host's
limits (api/limits.py) and the threat families. `/profiles` lists the companies a run can be
seeded from and makes new ones (api/routes_profiles.py). `/guard/tools` and
`/runs/{id}/guard/check` are Guard as an API: what the gate would say to a tool call, without
making it (api/routes_guard.py). `/health` is what a monitor or a reviewer reads: version,
commit, uptime, persistence, and how busy the server is.
"""

from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from vandal.api import (
    routes_blue,
    routes_guard,
    routes_hunt,
    routes_inject,
    routes_jobs,
    routes_policies,
    routes_profiles,
    routes_runs,
)
from vandal.api.db import Store
from vandal.api.limits import limits
from vandal.api.registry import JobsBusy, Registry
from vandal.llm import load_env, playback
from vandal.search.alphabet import SCENARIOS


def _version() -> str:
    try:
        return package_version("vandal")
    except PackageNotFoundError:
        return "0.0.0+local"


def _commit() -> str | None:
    """The deployed commit, from whichever host set it."""
    for var in ("VANDAL_COMMIT", "RENDER_GIT_COMMIT", "RAILWAY_GIT_COMMIT_SHA", "SOURCE_COMMIT"):
        if os.environ.get(var):
            return os.environ[var][:12]
    return None


class Settings(BaseModel):
    playback: bool


def create_app(store: Store | None = None, persist: bool | None = None) -> FastAPI:
    """`store` wins; otherwise persist when DATABASE_URL is set (or `persist` says so)."""
    load_env()
    if store is None and (persist if persist is not None else bool(os.environ.get("DATABASE_URL"))):
        store = Store()
        store.migrate()
    lim = limits()
    registry = Registry(
        store, max_jobs=lim.max_jobs, max_runs=lim.max_runs, jobs_per_owner=lim.jobs_per_client
    )
    started = time.monotonic()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        registry.shutdown()

    app = FastAPI(title="Vandal", version="0.1.0", lifespan=lifespan)
    app.state.registry = registry
    origins = os.environ.get("VANDAL_CORS_ORIGINS", "http://localhost:3000").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(JobsBusy)
    async def busy(_request: Request, err: JobsBusy) -> JSONResponse:
        return JSONResponse({"detail": str(err)}, status_code=429, headers={"Retry-After": "30"})

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "version": _version(),
            "commit": _commit(),
            "uptime_s": round(time.monotonic() - started),
            "persistence": store.dialect if store else None,
            "playback": playback(),
            "runs": len(registry.runs),
            "jobs": len(registry.jobs),
            "jobs_active": registry.active(),
            "limits": limits().as_dict(),
        }

    def settings() -> dict[str, object]:
        return {
            "playback": playback(),
            "api_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "limits": limits().as_dict(),
            # The threat families a search can be pointed at (search/alphabet.py), for a picker.
            "scenarios": {name: sc.description for name, sc in SCENARIOS.items()},
        }

    @app.get("/settings")
    def get_settings() -> dict[str, object]:
        return settings()

    @app.post("/settings")
    def set_settings(body: Settings) -> dict[str, object]:
        os.environ["DEMO_PLAYBACK"] = "true" if body.playback else "false"
        return settings()

    app.include_router(routes_runs.router)
    app.include_router(routes_inject.router)
    app.include_router(routes_hunt.router)
    app.include_router(routes_jobs.router)
    app.include_router(routes_policies.router)
    app.include_router(routes_profiles.router)
    app.include_router(routes_blue.router)
    app.include_router(routes_guard.router)
    return app


app = create_app()
