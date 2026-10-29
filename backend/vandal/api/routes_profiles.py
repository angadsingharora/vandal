"""The companies a run can be seeded from (twin/profile.py): the built-ins shipped as
profiles/*.yaml, and custom ones the workspace derives from them at runtime. A custom profile is
the base with a few knobs turned: the company's name, the approval matrix, how many invoices to
generate, what the attacker is allowed to do, and the risk appetite. It lives in the process like
a run does, and every job that takes a `profile` name accepts it."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from vandal.twin.profile import (
    Profile,
    builtin_profiles,
    custom_profiles,
    derive_profile,
    load_profile,
    register_profile,
)
from vandal.twin.seed import seed_state

router = APIRouter()

# A custom company is bounded so one visitor can't seed a run that takes the host down.
MAX_INVOICES = 400


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApprovalOverrides(_Body):
    threshold: int | None = Field(default=None, ge=0)  # cents
    match_tolerance_pct: int | None = Field(default=None, ge=0, le=50)
    min_prior_payments: int | None = Field(default=None, ge=0, le=20)
    aggregate_window_days: int | None = Field(default=None, ge=1, le=30)


class GenerationOverrides(_Body):
    invoices: int | None = Field(default=None, ge=1, le=MAX_INVOICES)
    pending_invoices: int | None = Field(default=None, ge=1, le=MAX_INVOICES)
    history_days: int | None = Field(default=None, ge=10, le=365)
    prior_contact_rate: float | None = Field(default=None, ge=0, le=1)
    prior_account_rate: float | None = Field(default=None, ge=0, le=1)


class AttackerOverrides(_Body):
    change_request_channels: list[str] | None = None
    senders: list[str] | None = None
    spoof_caller_id: bool | None = None
    clone_voice: bool | None = None
    portal_takeover: bool | None = None
    submit_invoices: bool | None = None
    deposits: bool | None = None


class RiskOverrides(_Body):
    lambda_per_blocked: int | None = Field(default=None, ge=0)
    mu_per_hold: int | None = Field(default=None, ge=0)


class OperatorOverrides(_Body):
    payment_horizon_days: int | None = Field(default=None, ge=1, le=60)


class NewProfile(_Body):
    """Everything optional: an empty body is a copy of the base under a new name."""

    name: str | None = Field(default=None, max_length=40)
    base: str = "bayline"
    company_name: str | None = Field(default=None, min_length=1, max_length=80)
    approval: ApprovalOverrides | None = None
    generation: GenerationOverrides | None = None
    attacker: AttackerOverrides | None = None
    risk: RiskOverrides | None = None
    operator: OperatorOverrides | None = None


def describe(name: str, p: Profile, custom: bool) -> dict[str, Any]:
    m = p.approval_matrix
    return {
        "name": name,
        "custom": custom,
        "company": p.company.name,
        "currency": p.company.currency,
        "properties": len(p.properties),
        "vendors": len(p.vendors),
        "customers": len(p.customers),
        "approval": {
            "threshold": m.threshold,
            "match_tolerance_pct": m.match_tolerance_pct,
            "min_prior_payments": m.min_prior_payments,
            "aggregate_window_days": m.aggregate_window_days,
            "approvers": [
                {"id": a.id, "name": a.name, "max_amount": a.max_amount} for a in m.approvers
            ],
        },
        "generation": p.generation.model_dump(),
        "attacker": p.attacker_capabilities.model_dump(),
        "risk": p.risk_appetite.model_dump(),
        "operator": {"payment_horizon_days": p.operator.payment_horizon_days},
        "fixtures": len(p.fixtures.invoices),
    }


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:40] or "company"


def _unique(slug: str) -> str:
    taken = set(builtin_profiles()) | set(custom_profiles())
    if slug not in taken:
        return slug
    for n in range(2, 1000):
        if f"{slug}-{n}" not in taken:
            return f"{slug}-{n}"
    raise HTTPException(400, "too many profiles with that name")


def _overrides(body: NewProfile) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if body.company_name:
        out["company"] = {"name": body.company_name}
    for key, section in (
        ("approval_matrix", body.approval),
        ("generation", body.generation),
        ("attacker_capabilities", body.attacker),
        ("risk_appetite", body.risk),
        ("operator", body.operator),
    ):
        if section is not None:
            given = section.model_dump(exclude_none=True)
            if given:
                out[key] = given
    return out


@router.get("/profiles")
def list_profiles() -> list[dict[str, Any]]:
    """The built-ins, then the custom companies made in this process."""
    out = [describe(n, load_profile(n), False) for n in builtin_profiles()]
    out += [describe(n, p, True) for n, p in custom_profiles().items()]
    return out


@router.get("/profiles/{name}")
def get_profile(name: str) -> dict[str, Any]:
    if name not in builtin_profiles() and name not in custom_profiles():
        raise HTTPException(404, f"no profile {name!r}")
    return describe(name, load_profile(name), name in custom_profiles())


@router.post("/profiles")
def create_profile(body: NewProfile) -> dict[str, Any]:
    """Derive a company from a base profile. It is seeded once here, so a combination the
    generator can't satisfy (more fixtures than pending invoices, say) fails now, not on the
    first run."""
    if body.base not in builtin_profiles() and body.base not in custom_profiles():
        raise HTTPException(400, f"unknown base profile {body.base!r}")
    base = load_profile(body.base)
    overrides = _overrides(body)
    try:
        profile = derive_profile(base, overrides)
    except ValueError as err:
        raise HTTPException(400, f"invalid profile: {err}") from None
    gen = profile.generation
    if gen.pending_invoices > gen.invoices:
        raise HTTPException(400, "pending_invoices can't exceed invoices")
    if gen.pending_invoices < len(profile.fixtures.invoices):
        raise HTTPException(
            400,
            f"pending_invoices must be at least {len(profile.fixtures.invoices)}, "
            "the base profile's fixture invoices",
        )
    try:
        seed_state(profile, seed=7)
    except Exception as err:  # the generator's own constraints
        raise HTTPException(400, f"the company can't be seeded: {err}") from None
    name = _unique(_slug(body.name or body.company_name or f"{body.base}-custom"))
    register_profile(name, profile)
    return describe(name, profile, True)
