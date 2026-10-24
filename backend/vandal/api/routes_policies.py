"""A0 routes for policies (R6). Applying one goes through the approvals inbox (routes_blue.py)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from vandal.api import deps
from vandal.synth.templates import available_policies, describe

router = APIRouter()


@router.get("/policies")
def list_policies(request: Request) -> list[dict[str, Any]]:
    """The built-ins, then policies applied through the inbox."""
    applied = [n for n in deps.registry(request).applied if n not in available_policies()]
    out = []
    for name in available_policies() + applied:
        p = deps.policy(name, request)
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
def get_policy(request: Request, name: str) -> dict[str, Any]:
    p = deps.policy(name, request)
    return {**p.model_dump(mode="json"), "described": [describe(c) for c in p.controls]}
