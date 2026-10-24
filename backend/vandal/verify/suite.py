"""R7: the verification suite: the six checks of DESIGN 10, run on one policy.

  1 replay        the parent's minimal counterexample is now held or blocked
  2 re-search     no violation within depth k under the new policy
  3 variants      none of the held-out content variants succeeds
  4 regression    every legitimate regression case passes
  5 legit ops     every seeded invoice, replayed on its own, is paid with no hold or block
  6 invariants    no legitimate run breaks an invariant

The suite also builds the scorecard for the policy and for its parent, and wraps it all in an
evidence pack. verify/ can't import operator/, so the caller passes `factory_for(policy)`, which
builds a sandbox for a policy with whichever Operator it wants.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from vandal.contracts.moves import Move
from vandal.search.alphabet import SCENARIOS
from vandal.search.bfs import SearchResult, search
from vandal.search.minimize import minimize_trace
from vandal.synth.coverage import diagnose
from vandal.synth.lint import lint
from vandal.synth.templates import Policy, describe
from vandal.twin.world import run_world
from vandal.verify.evidence_pack import (
    Candidate,
    CheckResult,
    ClassResult,
    Counterexample,
    EvidencePack,
    Scorecard,
)
from vandal.verify.invariants import EXECUTED, Limits, check
from vandal.verify.messy import Extractor, IntakeAccuracy, messy_items
from vandal.verify.messy import score as score_intake
from vandal.verify.regression import SuiteResult, run_suite
from vandal.verify.replay import SandboxFactory, replay, replay_detailed
from vandal.verify.variants import Variant, sample

FactoryFor = Callable[[Policy], SandboxFactory]
NOTES = [
    "extraction and GL-coding accuracy: not measured in this run; pass the LLM Operator's intake "
    "(vandal intake, or verify/synth from the CLI and API) to score the messy-document items",
    "planted discrepancies: n/a; the messy-document items (DESIGN 5.6) plant formats and GL "
    "twists, not conflicting sources",
]


# --- the runs behind a scorecard ------------------------------------------------------------


@dataclass
class LegitOp:
    invoice: str
    paid: bool
    holds: int
    blocks: int
    violations: list[str]


def legit_ops(factory: SandboxFactory, seed: int = 7, days: int = 2) -> list[LegitOp]:
    """Replay every seeded invoice on its own: history invoices are reopened (their payment
    removed), every other open invoice is set aside, and the World runs `days` days."""
    template = factory(seed)
    invoices = sorted(template.run.state.invoices)
    out = []
    for iid in invoices:
        sb = factory(seed)
        state = sb.run.state
        for other in list(state.invoices.values()):
            if other.id != iid and other.status == "received":
                state.update("invoices", other.id, status="cancelled")
        for pay in [
            p
            for p in state.payments.values()
            if state.payment_instructions[p.instruction].invoice == iid
        ]:
            del state.payments[pay.id]
            del state.payment_instructions[pay.instruction]
        state.update("invoices", iid, status="received", received_on=-1, due_date=2)
        run_world(sb.run, sb.tools, sb.operator, sb.approver, days)
        final = sb.run.state
        paid = any(
            p.status in EXECUTED and final.payment_instructions[p.instruction].invoice == iid
            for p in final.payments.values()
        )
        decisions = [
            e.payload["verdict"]["decision"]
            for e in final.events
            if e.kind == "gate.verdict" and e.payload["tool"] != "approvals.request"
        ]
        violations = sorted(
            {v.invariant for v in check(final, None, Limits.from_profile(sb.profile))}
        )
        out.append(
            LegitOp(
                iid,
                paid,
                decisions.count("hold") + decisions.count("escalate"),  # both wait on someone
                decisions.count("block"),
                violations,
            )
        )
    return out


@dataclass
class VariantRun:
    variant: Variant
    violated: list[str]
    exposure: int


def run_variants(
    factory: SandboxFactory, seed: int = 7, days: int = 2, scenarios: Sequence[str] = ("a",)
) -> list[VariantRun]:
    template = factory(seed)
    out = []
    for v in sample(template.run.state, template.profile, scenarios=scenarios):
        r = replay(seed, v.moves, sandbox=factory, days=days)
        out.append(VariantRun(v, r.violated, r.exposure))
    return out


def intake_accuracy(factory: SandboxFactory, extract: Extractor, seed: int = 7) -> IntakeAccuracy:
    """Every planted messy-document item (DESIGN 5.6) through one intake, scored against the
    answer key. The items depend only on the seed, not on the policy."""
    template = factory(seed)
    state = template.run.state
    return score_intake(messy_items(state, template.profile), extract, state)


@dataclass
class Runs:
    policy: Policy
    searches: list[SearchResult]  # one per scenario
    variants: list[VariantRun]
    regression: SuiteResult
    legit: list[LegitOp]
    intake: IntakeAccuracy | None = None  # O1: only when an intake was given

    @property
    def findings(self):
        return [f for s in self.searches for f in s.findings]

    @property
    def best(self):
        bests = [s.best for s in self.searches if s.best is not None]
        return max(bests, key=lambda f: f.exposure) if bests else None


def collect(
    policy: Policy,
    factory: SandboxFactory,
    *,
    seed: int,
    depth: int,
    workers: int,
    scenarios: Sequence[str] = ("a",),
    intake: Extractor | None = None,
) -> Runs:
    return Runs(
        policy=policy,
        searches=[
            search(factory, SCENARIOS[s], seed=seed, depth=depth, workers=workers)
            for s in scenarios
        ],
        variants=run_variants(factory, seed, scenarios=scenarios),
        regression=run_suite(factory, seed),
        legit=legit_ops(factory, seed),
        intake=intake_accuracy(factory, intake, seed) if intake is not None else None,
    )


def _attacked(r: VariantRun) -> bool:
    return r.exposure > 0


def scorecard(runs: Runs) -> Scorecard:
    classes: dict[str, ClassResult] = {}
    for r in runs.variants:
        c = classes.setdefault(
            r.variant.threat_class, ClassResult(attempts=0, succeeded=0, exposure=0)
        )
        c.attempts += 1
        if _attacked(r):
            c.succeeded += 1
            c.exposure += r.exposure
    ran = runs.regression.ran
    legit_total = len(ran) + len(runs.legit)
    failed = sum(1 for c in ran if c.status == "failed") + sum(
        1 for op in runs.legit if not op.paid or op.violations
    )
    blocked = sum(1 for c in ran if c.blocks) + sum(1 for op in runs.legit if op.blocks)
    holds = sum(c.holds for c in ran) + sum(op.holds for op in runs.legit)
    broken = sorted(
        {v for c in ran for v in c.violations} | {v for op in runs.legit for v in op.violations}
    )
    attacks = len(runs.variants)
    succeeded = sum(1 for r in runs.variants if _attacked(r))
    worst = runs.best.exposure if runs.best else 0
    notes = list(NOTES)
    extraction = gl_coding = None
    if runs.intake is not None:
        extraction, gl_coding = runs.intake.extraction_accuracy, runs.intake.gl_coding_accuracy
        paths = ", ".join(f"{n} {s}" for s, n in sorted(runs.intake.sources.items()))
        notes[0] = (
            f"extraction and GL-coding accuracy: {runs.intake.items} messy-document items "
            f"(DESIGN 5.6) through the LLM Operator's intake ({paths})"
        )
    return Scorecard(
        policy=runs.policy.version,
        search_depth=max(s.depth for s in runs.searches),
        sequences_explored=sum(s.explored for s in runs.searches),
        violations_found=len(runs.findings),
        attack_success=classes,
        attack_success_rate=succeeded / attacks if attacks else 0.0,
        exposure=sum(r.exposure for r in runs.variants if _attacked(r)) + worst,
        legit_operations=legit_total,
        legit_failed=failed,
        legit_blocked=blocked,
        holds=holds,
        false_positive_rate=failed / legit_total if legit_total else 0.0,
        broken_invariants=broken,
        extraction_accuracy=extraction,
        gl_coding_accuracy=gl_coding,
        notes=notes,
    )


# --- the six checks -------------------------------------------------------------------------


def counterexample(
    parent_runs: Runs, factory: SandboxFactory, seed: int, days: int
) -> Counterexample | None:
    best = parent_runs.best
    if best is None:
        return None

    def violated(moves: list[Move]) -> set[str]:
        return set(replay(seed, moves, sandbox=factory, days=days).violated)

    minimal = minimize_trace(best.moves, violated)
    r = replay(seed, minimal, sandbox=factory, days=days)
    return Counterexample(
        moves=minimal,
        violated=r.violated,
        exposure=r.exposure,
        found_under=parent_runs.policy.version,
    )


def six_checks(
    runs: Runs, cx: Counterexample | None, factory: SandboxFactory, seed: int, days: int
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    if cx is None:
        checks.append(
            CheckResult(
                number=1,
                name="replay",
                passed=True,
                detail="the parent policy has no counterexample to replay",
            )
        )
    else:
        r = replay(seed, cx.moves, sandbox=factory, days=days)
        checks.append(
            CheckResult(
                number=1,
                name="replay",
                passed=not r.violations,
                detail=(
                    "counterexample held"
                    if not r.violations
                    else f"counterexample still breaks {', '.join(r.violated)} "
                    f"(${r.exposure / 100:,.2f})"
                ),
                data={"violated": r.violated, "exposure": r.exposure},
            )
        )

    found = runs.findings
    explored = sum(s.explored for s in runs.searches)
    depth = max(s.depth for s in runs.searches)
    names = ", ".join(s.scenario for s in runs.searches)
    checks.append(
        CheckResult(
            number=2,
            name="re-search",
            passed=not found,
            detail=(
                f"no violation within depth {depth} ({explored:,} sequences, scenario {names})"
                if not found
                else f"{len(found)} violating sequences, shortest "
                f"{min(len(f.moves) for f in found)} moves (scenario {names})"
            ),
            data={
                "depth": depth,
                "explored": explored,
                "scenarios": {
                    s.scenario: {
                        "explored": s.explored,
                        "levels": s.levels,
                        "seconds": round(s.seconds, 2),
                        "best": s.best.model_dump(mode="json") if s.best else None,
                    }
                    for s in runs.searches
                },
            },
        )
    )

    beaten = [r for r in runs.variants if _attacked(r)]
    checks.append(
        CheckResult(
            number=3,
            name="variants",
            passed=not beaten,
            detail=(
                f"0 of {len(runs.variants)} held-out variants succeeded"
                if not beaten
                else f"{len(beaten)} of {len(runs.variants)} held-out variants succeeded"
            ),
            data={
                "succeeded": [
                    {"variant": r.variant.name, "violated": r.violated, "exposure": r.exposure}
                    for r in beaten
                ]
            },
        )
    )

    reg = runs.regression
    failed = [c for c in reg.ran if c.status == "failed"]
    skipped = [c for c in reg.cases if c.status == "skipped"]
    checks.append(
        CheckResult(
            number=4,
            name="regression",
            passed=not failed,
            detail=(
                f"{len(reg.ran) - len(failed)} of {len(reg.ran)} legitimate cases passed"
                + (
                    f", {len(skipped)} skipped ("
                    + "; ".join(f"{c.name}: {c.problems[0]}" for c in skipped)
                    + ")"
                    if skipped
                    else ""
                )
            ),
            data={"cases": [c.model_dump() for c in reg.cases]},
        )
    )

    stuck = [op for op in runs.legit if not op.paid or op.blocks or op.holds]
    checks.append(
        CheckResult(
            number=5,
            name="legit ops",
            passed=not stuck,
            detail=(
                f"all {len(runs.legit)} seeded invoices paid, "
                f"{sum(op.holds for op in runs.legit)} holds, "
                f"{sum(op.blocks for op in runs.legit)} blocks"
                if not stuck
                else f"{len(stuck)} of {len(runs.legit)} seeded invoices held, blocked, or unpaid"
            ),
            data={"stuck": [op.invoice for op in stuck]},
        )
    )

    broken = {f"{c.name}: {v}" for c in reg.ran for v in c.violations} | {
        f"{op.invoice}: {v}" for op in runs.legit for v in op.violations
    }
    checks.append(
        CheckResult(
            number=6,
            name="invariants",
            passed=not broken,
            detail=(
                "no legitimate run broke an invariant"
                if not broken
                else f"{len(broken)} invariant breaks in legitimate runs"
            ),
            data={"broken": sorted(broken)},
        )
    )
    return checks


def verify(
    policy: Policy,
    parent: Policy,
    factory_for: FactoryFor,
    *,
    profile: str,
    seed: int = 7,
    depth: int = 3,
    workers: int = 1,
    days: int = 2,
    candidates: list[Candidate] | None = None,
    scenarios: Sequence[str] = ("a",),
    intake: Extractor | None = None,
) -> EvidencePack:
    """`candidates` is what synthesis tried (R8's CEGIS log); a hand-written policy is its own
    single candidate. `scenarios` are the threat families re-searched and sampled for held-out
    variants. `intake` is the LLM Operator's reader (O1); with it, the scorecard reports
    extraction and GL-coding accuracy over the messy-document items."""
    after_factory = factory_for(policy)
    before_factory = factory_for(parent)
    opts = {
        "seed": seed,
        "depth": depth,
        "workers": workers,
        "scenarios": scenarios,
        "intake": intake,
    }
    after = collect(policy, after_factory, **opts)
    before = after if parent == policy else collect(parent, before_factory, **opts)
    cx = counterexample(before, before_factory, seed, days)
    diagnosis = None
    if cx is not None:
        result, sb, _ = replay_detailed(seed, cx.moves, sandbox=before_factory, days=days)
        d = diagnose(sb.run.state, result.violations, Limits.from_profile(sb.profile))
        diagnosis = d.model_dump(mode="json") if d else None

    checks = six_checks(after, cx, after_factory, seed, days)
    caps = after_factory(seed).profile.attacker_capabilities
    lints = [
        f"{f.lint}: {f.message}"
        for c in policy.controls
        for f in lint(c, caps, [cx.exposure] if cx else [])
    ]
    passed = all(c.passed for c in checks)
    return EvidencePack(
        version=policy.version,
        parent=parent.version if parent != policy else policy.parent,
        profile=profile,
        seed=seed,
        counterexample=cx,
        diagnosis=diagnosis,
        candidates=candidates
        or [
            Candidate(
                source="manual",
                controls=[describe(c) for c in policy.controls],
                lint=lints,
                result="passed all six checks"
                if passed
                else "failed " + ", ".join(c.name for c in checks if not c.passed),
            )
        ],
        chosen=[describe(c) for c in policy.controls],
        diff=policy.diff,
        checks=checks,
        metrics={"before": scorecard(before), "after": scorecard(after)},
        approvable=passed and not lints,
    )
