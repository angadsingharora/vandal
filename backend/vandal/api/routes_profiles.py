"""The companies a run can be seeded from (twin/profile.py): the built-ins shipped as
profiles/*.yaml, and custom ones the workspace derives from them at runtime. A custom profile is
the base with a few knobs turned: the company's name, its vendors' names and domains, the
approval matrix, how many invoices to generate, what the attacker is allowed to do, and the risk
appetite. It lives in the process like a run does, and every job that takes a `profile` name
accepts it.

A custom company is gone when the process restarts. `GET /profiles/{name}/export` hands the
whole profile back as JSON, and `POST /profiles/import` registers one again, so a company can
be kept in a file and brought back on any host."""

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
MAX_VENDORS = 60
_LABEL = r"[a-z0-9]([a-z0-9-]*[a-z0-9])?"
_DOMAIN = re.compile(rf"^(?=.{{4,80}}$){_LABEL}(\.{_LABEL})+$")


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


class VendorIn(_Body):
    """One of the user's vendors. It takes the place of one of the base company's vendors:
    the name and domain are theirs, the spend range, GL account and PO rule stay the base's,
    so the generated history still balances and the planted attack still has a target."""

    name: str = Field(min_length=1, max_length=80)
    domain: str | None = Field(default=None, max_length=80)


class NewProfile(_Body):
    """Everything optional: an empty body is a copy of the base under a new name."""

    name: str | None = Field(default=None, max_length=40)
    base: str = "bayline"
    company_name: str | None = Field(default=None, min_length=1, max_length=80)
    vendors: list[VendorIn] | None = Field(default=None, max_length=MAX_VENDORS)
    approval: ApprovalOverrides | None = None
    generation: GenerationOverrides | None = None
    attacker: AttackerOverrides | None = None
    risk: RiskOverrides | None = None
    operator: OperatorOverrides | None = None


class ImportProfile(_Body):
    """A whole profile, as `GET /profiles/{name}/export` gave it (or written by hand in the
    shape of profiles/*.yaml), under a name of the caller's choosing."""

    name: str | None = Field(default=None, max_length=40)
    profile: dict[str, Any]


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
        "vendor_names": [v.name for v in p.vendors],
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


def _domain_for(name: str, domain: str | None) -> str:
    if domain:
        d = domain.strip().lower()
        if not _DOMAIN.match(d):
            raise HTTPException(400, f"invalid domain {domain!r} for vendor {name!r}")
        return d
    return f"{_slug(name).replace('-', '')[:30] or 'vendor'}.com"


def _with_vendors(base: Profile, given: list[VendorIn]) -> list[dict[str, Any]]:
    """The base's vendor list with the first len(given) entries renamed in place."""
    if len(given) > len(base.vendors):
        raise HTTPException(
            400, f"at most {len(base.vendors)} vendors: the base company has that many"
        )
    seen: set[str] = set()
    out = [v.model_dump() for v in base.vendors]
    for spec, v in zip(out, given, strict=False):
        key = v.name.strip().lower()
        if key in seen:
            raise HTTPException(400, f"vendor {v.name!r} is listed twice")
        seen.add(key)
        spec["name"] = v.name.strip()
        spec["domain"] = _domain_for(v.name, v.domain)
    return out


def _overrides(body: NewProfile, base: Profile) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if body.company_name:
        out["company"] = {"name": body.company_name}
    if body.vendors:
        out["vendors"] = _with_vendors(base, body.vendors)
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
    overrides = _overrides(body, base)
    try:
        profile = derive_profile(base, overrides)
    except ValueError as err:
        raise HTTPException(400, f"invalid profile: {err}") from None
    _check(profile)
    name = _unique(_slug(body.name or body.company_name or f"{body.base}-custom"))
    register_profile(name, profile)
    return describe(name, profile, True)


def _check(profile: Profile) -> None:
    """The bounds a custom company has to meet, and one seeding to prove it can be."""
    gen = profile.generation
    if gen.invoices > MAX_INVOICES:
        raise HTTPException(400, f"invoices can't exceed {MAX_INVOICES}")
    if len(profile.vendors) > MAX_VENDORS:
        raise HTTPException(400, f"at most {MAX_VENDORS} vendors")
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


@router.get("/profiles/{name}/export")
def export_profile(name: str) -> dict[str, Any]:
    """The whole profile as JSON: keep it in a file, import it on any host."""
    if name not in builtin_profiles() and name not in custom_profiles():
        raise HTTPException(404, f"no profile {name!r}")
    profile = load_profile(name)
    return {
        "name": name,
        "company": profile.company.name,
        "profile": profile.model_dump(mode="json"),
    }


@router.post("/profiles/import")
def import_profile(body: ImportProfile) -> dict[str, Any]:
    """Register a profile from its exported JSON. Validated like a file, bounded like a custom
    company, seeded once to prove it works."""
    try:
        profile = Profile.model_validate(body.profile)
    except ValueError as err:
        raise HTTPException(400, f"invalid profile: {err}") from None
    _check(profile)
    name = _unique(_slug(body.name or profile.company.name))
    register_profile(name, profile)
    return describe(name, profile, True)
