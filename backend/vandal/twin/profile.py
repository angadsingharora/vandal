"""R1: the company profile (DESIGN 5.5), loaded from profiles/*.yaml."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

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


class ApprovalMatrix(_Spec):
    threshold: Cents
    match_tolerance_pct: int
    approvers: list[ApproverSpec]
    min_prior_payments: int


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
    fixtures: Fixtures = Field(default_factory=Fixtures)


def load_profile(name_or_path: str | Path = "bayline") -> Profile:
    path = Path(name_or_path)
    if not path.suffix:
        path = PROFILES_DIR / f"{name_or_path}.yaml"
    return Profile.model_validate(yaml.safe_load(path.read_text()))
