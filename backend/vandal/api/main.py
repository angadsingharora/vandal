"""A0: the FastAPI app.

    uv run uvicorn vandal.api.main:app --reload

Runs live in memory (api/registry.py). With DATABASE_URL set, every run's events and every
search, synthesis, and evidence pack are also persisted (api/db.py, R12). The war-room frontend
reads state over JSON and follows runs and jobs over SSE.

`/settings` holds the demo switches the war room flips: LLM playback (DEMO_PLAYBACK, read by
vandal/llm.py) for this server process.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from vandal.api import routes_blue, routes_inject, routes_jobs, routes_policies, routes_runs
from vandal.api.db import Store
from vandal.api.registry import Registry
from vandal.llm import load_env


class Settings(BaseModel):
    playback: bool


def create_app(store: Store | None = None, persist: bool | None = None) -> FastAPI:
    """`store` wins; otherwise persist when DATABASE_URL is set (or `persist` says so)."""
    load_env()
    if store is None and (persist if persist is not None else bool(os.environ.get("DATABASE_URL"))):
        store = Store()
        store.migrate()
    registry = Registry(store)

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

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "persistence": store.dialect if store else None,
            "runs": len(registry.runs),
            "jobs": len(registry.jobs),
        }

    def settings() -> dict[str, object]:
        return {
            "playback": os.environ.get("DEMO_PLAYBACK", "false").lower() == "true",
            "api_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
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
    app.include_router(routes_jobs.router)
    app.include_router(routes_policies.router)
    app.include_router(routes_blue.router)
    return app


app = create_app()
