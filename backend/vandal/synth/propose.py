"""R8: candidate controls for a diagnosed gap.

Two proposers, the same output:

  SweepProposer  enumerates the parameters of the templates that close the gap, simplest and
                 least restrictive first. Deterministic, no model; always available.
  LLMProposer    Claude (MODEL_SYNTH, through vandal/llm.py) reads the diagnosis, the policy,
                 the template catalog, and what has been refuted so far, and returns candidates
                 as structured output (template + params + rationale). If the model is
                 unavailable or returns nothing usable, it falls back to the sweep.

Either way the proposer only *proposes*: every candidate is validated by its template, linted,
searched, and regression-checked by CEGIS before anything is kept (DESIGN 4: the AI proposes,
search and verification decide).
"""

from __future__ import annotations

import json
from itertools import combinations
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from vandal.contracts.controls import Control
from vandal.synth.templates import NAMES, PARAMS, describe, params_of
from vandal.twin.profile import Profile

# Which templates can close which gap (DESIGN 9.1 -> 9.2).
GAP_TEMPLATES: dict[str, tuple[str, ...]] = {
    "approval_binding": ("T2",),
    "verification_channel": ("T1",),
    "execution_idempotency": ("T3",),
    "duplicate_obligation": ("T4",),
    "aggregate_threshold": ("T5",),
    "refund_destination": ("T6",),
}
EVIDENCE_CHANNELS = ("phone_outbound", "portal", "phone_in", "video", "email")


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    controls: list[Control]  # added on top of the base policy
    rationale: str
    source: str  # "sweep" or "llm"

    @property
    def label(self) -> str:
        return " + ".join(describe(c) for c in self.controls)


class Refutation(BaseModel):
    """What CEGIS learned about a candidate: fed back to the proposer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate: str
    outcome: str  # lint | counterexample | false_positive
    detail: str


class ProposalContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iteration: int
    gap: str
    diagnosis: dict
    base: list[Control]  # controls already kept from earlier iterations
    feedback: list[Refutation]
    tried: list[str]  # labels already evaluated


class Proposer(Protocol):
    name: str

    def propose(self, ctx: ProposalContext) -> list[Proposal]: ...


# --- the sweep ------------------------------------------------------------------------------


def _grid(template: str, profile: Profile) -> list[dict]:
    """Parameter combinations, simplest and least restrictive first."""
    threshold = profile.approval_matrix.threshold
    match template:
        case "T1":
            subsets = [
                list(c)
                for n in range(1, len(EVIDENCE_CHANNELS) + 1)
                for c in combinations(EVIDENCE_CHANNELS, n)
            ]
            return [
                {"accepted_channels": s, "contact_as_of": as_of, "window_days": 30}
                for s in subsets
                for as_of in ("current", "before_request")
            ]
        case "T2":
            return [
                {"bound_fields": f, "on_mismatch": m}
                for f in (
                    ["payee_account"],
                    ["amount", "payee_account"],
                    ["amount", "payee_account", "due_date"],
                )
                for m in ("hold", "reapprove")
            ]
        case "T3":
            return [
                {"key_fields": k, "on_timeout": t}
                for k in (["invoice"], ["invoice", "approval"])
                for t in ("query_status_then_retry", "retry_with_key")
            ]
        case "T4":
            return [
                {"amount_tol_pct": tol, "window_days": w, "normalize_number": True}
                for w in (10, 30)
                for tol in (0, 1, 2)
            ]
        case "T5":
            return [{"window_days": w, "threshold": threshold} for w in (5, 10)]
        case "T6":
            return [
                {"allowed": a, "require_cleared_funds": cleared, "cooling_days": 0}
                for cleared in (False, True)
                for a in ("source_only", "source_or_verified")
            ]
    return []


class SweepProposer:
    name = "sweep"

    def __init__(self, profile: Profile) -> None:
        self.profile = profile

    def propose(self, ctx: ProposalContext) -> list[Proposal]:
        out = []
        for template in GAP_TEMPLATES.get(ctx.gap, ()):
            for params in _grid(template, self.profile):
                control = Control(template=template, params=params)
                proposal = Proposal(
                    controls=[control],
                    source="sweep",
                    rationale=f"{NAMES[template]} closes {ctx.gap}; sweeping its parameters",
                )
                if proposal.label not in ctx.tried:
                    out.append(proposal)
        return out


# --- Claude ---------------------------------------------------------------------------------

PROMPT_VERSION = "synth-v2"  # v2: params as key/value pairs (a free-form dict comes back empty)
SYSTEM = (
    "You repair financial controls. You may only propose controls from the template catalog, "
    "with parameters that fit each template's schema, given as key/value pairs under "
    "`params`. A candidate is refuted by a "
    "counterexample (an attack search still finds), a false positive (a legitimate operation "
    "it breaks), or a lint (it is overfit, spoofable, or blocks where a hold works). Learn from "
    "the refutations. Prefer the least restrictive control that closes the gap."
)


class _LLMParam(BaseModel):
    key: str
    value: str | int | list[str]


class _LLMCandidate(BaseModel):
    template: str
    # Structured output can't fill a free-form dict (it comes back as {}), so a template's
    # parameters travel as key/value pairs and are folded into Control.params here.
    params: list[_LLMParam] = Field(default_factory=list)
    rationale: str


class _LLMProposal(BaseModel):
    candidates: list[_LLMCandidate] = Field(max_length=6)


def catalog() -> dict:
    return {t: {"name": NAMES[t], "params": PARAMS[t].model_json_schema()} for t in NAMES}


class LLMProposer:
    name = "llm"

    def __init__(self, profile: Profile, fallback: Proposer | None = None) -> None:
        self.fallback = fallback or SweepProposer(profile)
        self.notes: list[str] = []

    def propose(self, ctx: ProposalContext) -> list[Proposal]:
        from vandal.llm import LLMUnavailable, structured

        prompt = json.dumps(
            {
                "gap": ctx.gap,
                "diagnosis": {
                    k: ctx.diagnosis.get(k) for k in ("gap", "link", "reason", "violated")
                },
                "current_controls": [describe(c) for c in ctx.base],
                "templates_for_gap": list(GAP_TEMPLATES.get(ctx.gap, ())),
                "catalog": catalog(),
                "refuted": [r.model_dump() for r in ctx.feedback],
            },
            sort_keys=True,
        )
        try:
            reply = structured(
                agent="synth",
                step=f"propose-{ctx.iteration}",
                prompt_version=PROMPT_VERSION,
                system=SYSTEM,
                prompt=prompt,
                schema=_LLMProposal,
            )
        except LLMUnavailable as err:
            self.notes.append(f"iteration {ctx.iteration}: LLM unavailable ({err}); sweep")
            return self.fallback.propose(ctx)
        out = []
        for c in reply.candidates:
            try:
                control = Control(template=c.template, params={p.key: p.value for p in c.params})
                params_of(control)
            except (ValidationError, KeyError, ValueError) as err:
                self.notes.append(f"iteration {ctx.iteration}: dropped invalid {c.template}: {err}")
                continue
            p = Proposal(controls=[control], rationale=c.rationale, source="llm")
            if p.label not in ctx.tried and p.label not in {o.label for o in out}:
                out.append(p)
        if not out:
            self.notes.append(f"iteration {ctx.iteration}: no usable LLM candidates; sweep")
            return self.fallback.propose(ctx)
        return out
