"""A0 routes for policies (R6). Applying a patch needs the approvals inbox (B3), not yet built."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from vandal.api import deps
from vandal.synth.templates import available_policies, describe

router = APIRouter()


@router.get("/policies")
def list_policies() -> list[dict[str, Any]]:
    out = []
    for name in available_policies():
        p = deps.policy(name)
        out.append(
            {
                "name": name,
                "version": p.version,
                "parent": p.parent,
                "controls": [describe(c) for c in p.controls],
                "diff": p.diff,
            }
        )
    return out


@router.get("/policies/{name}")
def get_policy(name: str) -> dict[str, Any]:
    p = deps.policy(name)
    return {**p.model_dump(mode="json"), "described": [describe(c) for c in p.controls]}
