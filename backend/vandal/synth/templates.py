"""R6: control templates T1-T6 (DESIGN 9.2) and the policy store.

A Control is a template plus parameters. It compiles to gate Checks over deterministic facts
(twin/facts.py), and those are the only things the synthesizer can install. A Policy is v0 plus
a list of Controls, with a parent version and a readable diff.

Every template validates its parameters, so a candidate that isn't a valid control fails here,
before lints or search see it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vandal.contracts.controls import Check, Condition, Control, Decision, Predicate, Requirement
from vandal.contracts.entities import Cents, EvidenceChannel
from vandal.twin.facts import WINDOWS
from vandal.twin.profile import Profile

NAMES = {
    "T1": "VerifiedAccountChange",
    "T2": "ApprovalBinding",
    "T3": "IdempotentExecution",
    "T4": "DuplicateObligationGuard",
    "T5": "AggregateApprovalThreshold",
    "T6": "RefundToSource",
}


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class T1Params(_Params):
    accepted_channels: list[EvidenceChannel] = Field(min_length=1)
    contact_as_of: Literal["current", "before_request"] = "before_request"
    window_days: int = Field(default=30, ge=1)


class T2Params(_Params):
    bound_fields: list[Literal["amount", "payee_account", "due_date"]] = Field(min_length=1)
    on_mismatch: Literal["hold", "reapprove", "block"] = "hold"


class T3Params(_Params):
    key_fields: list[Literal["invoice", "approval", "instruction_hash"]] = ["invoice"]
    on_timeout: Literal["query_status_then_retry", "retry_with_key"] = "query_status_then_retry"


class T4Params(_Params):
    amount_tol_pct: int = Field(default=0, ge=0, le=100)
    window_days: int = 30
    normalize_number: bool = True
    action: Literal["hold", "block"] = "hold"

    @field_validator("window_days")
    @classmethod
    def _known_window(cls, v: int) -> int:
        if v not in WINDOWS:
            raise ValueError(f"window_days must be one of {WINDOWS}")
        return v


class T5Params(_Params):
    group_by: Literal["vendor"] = "vendor"
    window_days: int = 5
    threshold: Cents = Field(gt=0)

    @field_validator("window_days")
    @classmethod
    def _known_window(cls, v: int) -> int:
        if v not in WINDOWS:
            raise ValueError(f"window_days must be one of {WINDOWS}")
        return v


class T6Params(_Params):
    allowed: Literal["source_only", "source_or_verified"] = "source_only"
    require_cleared_funds: bool = True
    cooling_days: int = Field(default=0, ge=0)


PARAMS: dict[str, type[_Params]] = {
    "T1": T1Params,
    "T2": T2Params,
    "T3": T3Params,
    "T4": T4Params,
    "T5": T5Params,
    "T6": T6Params,
}


def params_of(control: Control) -> _Params:
    return PARAMS[control.template].model_validate(control.params)


def _when(*conditions: tuple[str, str, object]) -> Predicate:
    return Predicate(all=[Condition(fact=f, op=op, value=v) for f, op, v in conditions])


def _tag(control: Control) -> str:
    canonical = json.dumps(params_of(control).model_dump(mode="json"), sort_keys=True)
    return f"{control.template}[{hashlib.sha256(canonical.encode()).hexdigest()[:6]}]"


def compile_control(control: Control) -> list[Check]:
    p = params_of(control)
    tag = _tag(control)
    match p:
        case T1Params():
            accepted = list(p.accepted_channels)
            return [
                Check(
                    id=f"{tag}.change",
                    stage="change_request",
                    when=_when(
                        ("tool", "in", ["vendors.change_request", "vendors.apply_change"]),
                        ("change.bank", "eq", True),
                    ),
                    action="hold",
                    require=Requirement(
                        accepted_channels=accepted,
                        contact_as_of=p.contact_as_of,
                        window_days=p.window_days,
                    ),
                ),
                Check(
                    id=f"{tag}.payee_verified",
                    stage="pre_execute",
                    when=_when(("payee_account.status", "ne", "verified")),
                    action="hold",
                ),
                Check(
                    id=f"{tag}.payee_channel",
                    stage="pre_execute",
                    when=_when(("payee_account.verified_by", "not_in", accepted)),
                    action="hold",
                ),
            ]
        case T2Params():
            action: Decision = {"hold": "hold", "reapprove": "escalate", "block": "block"}[
                p.on_mismatch
            ]
            return [
                Check(
                    id=f"{tag}.{field}",
                    stage="pre_execute",
                    when=_when((f"binding.{field}_matches", "eq", False)),
                    action=action,
                )
                for field in p.bound_fields
            ]
        case T3Params():
            checks = [
                Check(
                    id=f"{tag}.once",
                    stage="submit",
                    when=_when(("invoice.other_executions", "gt", 0)),
                    action="block",
                )
            ]
            if p.on_timeout == "query_status_then_retry":
                # Ask the bank before resending; never resend what it already processed.
                retry = ("tool", "eq", "payments.retry")
                checks += [
                    Check(
                        id=f"{tag}.query_first",
                        stage="retry",
                        when=_when(retry, ("payment.bank_status", "eq", "unknown")),
                        action="hold",
                    ),
                    Check(
                        id=f"{tag}.already_processed",
                        stage="retry",
                        when=_when(retry, ("payment.bank_status", "eq", "processed")),
                        action="block",
                    ),
                ]
            else:  # retry_with_key: every submission carries a key, so the bank dedupes
                checks += [
                    Check(
                        id=f"{tag}.key",
                        stage=stage,
                        when=_when(
                            ("tool", "in", ["payments.submit", "payments.retry"]),
                            ("submit.has_key", "eq", False),
                        ),
                        action="hold",
                    )
                    for stage in ("submit", "retry")
                ]
            return checks
        case T4Params():
            checks = [
                Check(
                    id=f"{tag}.amount",
                    stage="invoice.match",
                    when=_when((f"dup.amount_bps.{p.window_days}d", "lte", p.amount_tol_pct * 100)),
                    action=p.action,
                )
            ]
            if p.normalize_number:
                checks.insert(
                    0,
                    Check(
                        id=f"{tag}.number",
                        stage="invoice.match",
                        when=_when(("dup.normalized_number", "eq", True)),
                        action=p.action,
                    ),
                )
            return checks
        case T5Params():
            return [
                Check(
                    id=f"{tag}.aggregate",
                    stage="pre_approve",
                    when=_when(
                        ("tool", "eq", "approvals.request"),
                        (f"vendor.window_total.{p.window_days}d", "gt", p.threshold),
                    ),
                    action="escalate",
                )
            ]
        case T6Params():
            checks = [
                Check(
                    id=f"{tag}.destination",
                    stage="refund",
                    when=_when(
                        ("refund.to_source", "eq", False),
                        *(
                            [("refund.to_verified", "eq", False)]
                            if p.allowed == "source_or_verified"
                            else []
                        ),
                    ),
                    action="hold",
                )
            ]
            if p.require_cleared_funds:
                checks.append(
                    Check(
                        id=f"{tag}.cleared_funds",
                        stage="refund",
                        when=_when(("refund.funds_cleared", "eq", False)),
                        action="hold",
                    )
                )
            if p.cooling_days:
                checks.append(
                    Check(
                        id=f"{tag}.cooling",
                        stage="refund",
                        when=_when(("refund.deposit_age_days", "lt", p.cooling_days)),
                        action="hold",
                    )
                )
            return checks
    raise ValueError(f"unknown template {control.template}")


def describe(control: Control) -> str:
    p = params_of(control).model_dump(mode="json")
    args = ", ".join(f"{k}={v}" for k, v in p.items())
    return f"{control.template} {NAMES[control.template]}({args})"


# --- policies -------------------------------------------------------------------------------


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    controls: list[Control] = []
    parent: str | None = None
    diff: list[str] = []

    def checks(self, profile: Profile) -> list[Check]:
        from vandal.guard.checks import v0_checks

        return v0_checks(profile.approval_matrix) + [
            c for control in self.controls for c in control.compile()
        ]

    @classmethod
    def load(cls, path: str | Path) -> Policy:
        data = json.loads(Path(path).read_text())
        policy = cls.model_validate(data)
        for control in policy.controls:
            params_of(control)  # fail on load, not at the gate
        if not policy.diff:
            policy = policy.model_copy(
                update={"diff": [f"+ {describe(c)}" for c in policy.controls]}
            )
        return policy


V0 = Policy(version="v0")
POLICIES_DIR = Path(__file__).resolve().parents[2] / "policies"


def load_policy(name: str | None) -> Policy:
    """`v0`, a name under policies/ (`v1` -> policies/v1.json), or a path."""
    if not name or name == "v0":
        return V0
    path = Path(name)
    if not path.suffix:
        path = POLICIES_DIR / f"{name}.json"
    return Policy.load(path)


def available_policies() -> list[str]:
    return ["v0"] + sorted(p.stem for p in POLICIES_DIR.glob("*.json"))


class PolicyStore:
    """Versions by name. Each new version records its parent and what changed."""

    def __init__(self) -> None:
        self.versions: dict[str, Policy] = {"v0": V0}

    def derive(
        self, parent: str, version: str, add: list[Control] = (), remove: list[Control] = ()
    ) -> Policy:
        if version in self.versions:
            raise ValueError(f"{version} already exists")
        base = self.versions[parent]
        controls = [c for c in base.controls if c not in remove] + [
            c for c in add if c not in base.controls
        ]
        diff = [f"- {describe(c)}" for c in remove if c in base.controls]
        diff += [f"+ {describe(c)}" for c in add if c not in base.controls]
        policy = Policy(version=version, controls=controls, parent=parent, diff=diff)
        self.versions[version] = policy
        return policy
