"""R1: the company profile (DESIGN 5.5), loaded from profiles/*.yaml."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from vandal.contracts.entities import Cents, SimDay

PROFILES_DIR = Path(__file__).resolve().parents[2] / "profiles"


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CompanySpec(_Spec):
    name: str
    start_date: date
    currency: str = "USD"


class PropertySpec(_Spec):
    id: str
    name: str


class BankAccountSpec(_Spec):
    id: str
    name: str
    gl_account: str
    balance: Cents


class LedgerAccountSpec(_Spec):
    id: str
    name: str
    kind: Literal["asset", "liability", "equity", "revenue", "expense"]


class ApproverSpec(_Spec):
    id: str
    name: str
    max_amount: Cents | None
    response_days: int = 0  # how long the simulated approver takes to answer (O3)


class ApprovalMatrix(_Spec):
    threshold: Cents
    match_tolerance_pct: int
    approvers: list[ApproverSpec]
    min_prior_payments: int
    aggregate_window_days: int = 5  # INV-6: per-vendor totals in this window count


class OperatorSpec(_Spec):
    id: str
    payment_horizon_days: int = 10  # the batch pays approved invoices due within this window


class AttackerCapabilities(_Spec):
    change_request_channels: list[str]
    senders: list[str]
    spoof_caller_id: bool
    clone_voice: bool
    portal_takeover: bool
    submit_invoices: bool
    deposits: bool

    @model_validator(mode="after")
    def _portal_needs_takeover(self) -> AttackerCapabilities:
        # A portal submission is authenticated evidence on its own (twin/flows), so an attacker
        # can only send one by taking the portal over.
        if "portal" in self.change_request_channels and not self.portal_takeover:
            raise ValueError("change_request_channels has portal but portal_takeover is false")
        return self


class RiskAppetite(_Spec):
    lambda_per_blocked: Cents
    mu_per_hold: Cents


class GenerationSpec(_Spec):
    invoices: int
    pending_invoices: int
    history_days: int
    prior_contact_rate: float
    prior_account_rate: float


class VendorSpec(_Spec):
    id: str
    name: str
    domain: str
    gl: str
    min: Cents
    max: Cents
    po: bool


class CustomerSpec(_Spec):
    """A tenant (money in, R11): open rent invoices, and the account they pay from."""

    id: str
    name: str
    property: str
    rent: Cents
    open_invoices: int = 1


class FixtureInvoice(_Spec):
    id: str
    vendor: str
    number: str
    amount: Cents
    dimension: str
    received_on: SimDay
    due_date: SimDay
    po: bool


class Fixtures(_Spec):
    invoices: list[FixtureInvoice] = []
    min_prior_payments: dict[str, int] = {}


class Profile(_Spec):
    company: CompanySpec
    properties: list[PropertySpec]
    bank_accounts: list[BankAccountSpec]
    chart_of_accounts: list[LedgerAccountSpec]
    opening_equity_account: str
    approval_matrix: ApprovalMatrix
    operator: OperatorSpec
    attacker_capabilities: AttackerCapabilities
    risk_appetite: RiskAppetite
    generation: GenerationSpec
    vendors: list[VendorSpec]
    customers: list[CustomerSpec] = []
    fixtures: Fixtures = Field(default_factory=Fixtures)


# Profiles made at runtime (the workspace's custom companies, api/routes_profiles.py). They live
# as long as the process, like runs do, and resolve by name wherever a profile name is accepted.
_CUSTOM: dict[str, Profile] = {}


def load_profile(name_or_path: str | Path = "bayline") -> Profile:
    if isinstance(name_or_path, str) and name_or_path in _CUSTOM:
        return _CUSTOM[name_or_path]
    path = Path(name_or_path)
    if not path.suffix:
        path = PROFILES_DIR / f"{name_or_path}.yaml"
    return Profile.model_validate(yaml.safe_load(path.read_text()))


def builtin_profiles() -> list[str]:
    """The profiles shipped as profiles/*.yaml, by name."""
    return sorted(p.stem for p in PROFILES_DIR.glob("*.yaml"))


def custom_profiles() -> dict[str, Profile]:
    return dict(_CUSTOM)


def register_profile(name: str, profile: Profile) -> None:
    if name in builtin_profiles():
        raise ValueError(f"{name!r} is a built-in profile")
    _CUSTOM[name] = profile


def clear_custom_profiles() -> None:
    _CUSTOM.clear()


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def derive_profile(base: Profile, overrides: dict) -> Profile:
    """A new profile from `base` with nested `overrides` applied (a dict shaped like the YAML,
    any subset of its keys). Validation is the same as for a file."""
    return Profile.model_validate(_merge(base.model_dump(mode="python"), overrides))
