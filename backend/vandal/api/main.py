"""A0: FastAPI app. Routes are added per slice as each one lands."""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Vandal")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
