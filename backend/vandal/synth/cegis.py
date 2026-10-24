"""R8: counterexample-guided synthesis (DESIGN 9.3).

    gap -> propose candidates -> lint -> regression + legit ops -> search under base+candidate
          ^                                                                     |
          +---- counterexample or false positive goes back as feedback ---------+

Each iteration proposes controls for the current gap and evaluates up to `per_iteration` of
them that pass lint. A candidate is refuted by:

  lint            overfit, spoofable, or blocks where a hold works (cheapest, checked first)
  false positive  a legitimate operation fails, or breaks an invariant (no search spent)
  counterexample  search still finds a violation within depth k

If any candidate survives, the one with the best objective (synth/objective.py) wins. If not,
the refuted candidate with the best objective becomes the base, its counterexample is diagnosed,
and the next iteration works on that gap: e.g. T2 closes the approval-binding gap, search finds
a change *before* approval, and the next iteration adds T1. After `max_iterations` without a
survivor the honest answer is "cannot auto-repair within templates", with the evidence.

synth/ can't import operator/, so the caller passes `factory_for(policy)`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from vandal.contracts.controls import Control
from vandal.contracts.entities import OracleLabel
from vandal.contracts.moves import Move
from vandal.search.alphabet import SCENARIOS
from vandal.search.bfs import search
from vandal.search.minimize import minimize_trace
from vandal.synth.coverage import diagnose
from vandal.synth.lint import lint
from vandal.synth.objective import Measurement, rank, score
from vandal.synth.propose import Proposal, ProposalContext, Proposer, Refutation
from vandal.synth.templates import Policy, describe, params_of
from vandal.twin.profile import Profile
from vandal.verify.invariants import Limits
from vandal.verify.regression import run_suite
from vandal.verify.replay import SandboxFactory, replay, replay_detailed
from vandal.verify.suite import legit_ops

FactoryFor = Callable[[Policy], SandboxFactory]
Outcome = Literal["lint", "false_positive", "counterexample", "survived"]


class LogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iteration: int
    gap: str
    candidate: str  # what this iteration added
    base: list[str]  # kept from earlier iterations
    source: str
    rationale: str
    outcome: Outcome
    detail: str
    lint: list[str] = []
    counterexample: list[Move] | None = None
    violated: list[str] = []
    measurement: Measurement | None = None
    score: int | None = None


class CEGISResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["repaired", "cannot_auto_repair", "nothing_to_repair"]
    reason: str
    policy: Policy | None = None
    chosen: list[str] = []
    score: int | None = None
    iterations: int
    log: list[LogEntry]
    notes: list[str] = []


def _param_count(controls: list[Control]) -> int:
    n = 0
    for c in controls:
        for v in params_of(c).model_dump().values():
            n += len(v) if isinstance(v, list) else 1
    return n


class _Evaluated(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal: Proposal
    entry: LogEntry
    diagnosis: dict | None = None


def cegis(
    parent: Policy,
    factory_for: FactoryFor,
    *,
    profile: Profile,
    proposer: Proposer,
    seed: int = 7,
    depth: int = 3,
    workers: int = 1,
    days: int = 2,
    max_iterations: int = 4,
    per_iteration: int = 4,
    version: str = "v1-synth",
    on_entry: Callable[[LogEntry], None] | None = None,
    start: list[Move] | None = None,
    start_labels: Sequence[OracleLabel] = (),
) -> CEGISResult:
    """`start` is a counterexample to repair (an injected threat, R9) instead of the one the
    parent's own search finds; `start_labels` is that trace's answer key."""
    scenario = SCENARIOS["a"]
    risk = profile.risk_appetite
    log: list[LogEntry] = []

    def record(entry: LogEntry) -> LogEntry:
        log.append(entry)
        if on_entry:
            on_entry(entry)
        return entry

    def counterexample(factory: SandboxFactory, best_moves: list[Move]):
        def violated(moves: list[Move]) -> set[str]:
            return set(
                replay(seed, moves, sandbox=factory, days=days, labels=start_labels).violated
            )

        minimal = minimize_trace(best_moves, violated)
        result, sb, _ = replay_detailed(
            seed, minimal, sandbox=factory, days=days, labels=start_labels
        )
        d = diagnose(sb.run.state, result.violations, Limits.from_profile(sb.profile))
        return minimal, result, (d.model_dump(mode="json") if d else None)

    # The parent's counterexample and its root cause start the loop.
    parent_factory = factory_for(parent)
    if start is not None:
        if not replay(
            seed, start, sandbox=parent_factory, days=days, labels=start_labels
        ).violations:
            return CEGISResult(
                status="nothing_to_repair",
                iterations=0,
                log=log,
                reason=f"the given trace breaks nothing under {parent.version}",
            )
        cx_moves, cx_result, diagnosis = counterexample(parent_factory, list(start))
    else:
        found = search(parent_factory, scenario, seed=seed, depth=depth, workers=workers)
        if found.best is None:
            return CEGISResult(
                status="nothing_to_repair",
                iterations=0,
                log=log,
                reason=f"{parent.version} has no violation within depth {depth}",
            )
        cx_moves, cx_result, diagnosis = counterexample(parent_factory, found.best.moves)
    injected = cx_moves if start is not None else None  # every candidate must hold against it
    if diagnosis is None:
        return CEGISResult(
            status="cannot_auto_repair",
            iterations=0,
            log=log,
            reason="the counterexample's chains are all covered; nothing to attach a template to",
        )

    legit_cache: dict[str, tuple[list[str], int, int]] = {}

    def legit(policy: Policy) -> tuple[list[str], int, int]:
        """(failed legitimate operations, blocks, holds) under a policy, cached by controls."""
        key = "|".join(describe(c) for c in policy.controls)
        if key not in legit_cache:
            factory = factory_for(policy)
            suite = run_suite(factory, seed)
            ops = legit_ops(factory, seed, days)
            failed = [c.name for c in suite.ran if c.status == "failed"] + [
                op.invoice for op in ops if not op.paid or op.violations
            ]
            blocked = sum(1 for c in suite.ran if c.blocks) + sum(1 for op in ops if op.blocks)
            holds = sum(c.holds for c in suite.ran) + sum(op.holds for op in ops)
            legit_cache[key] = (failed, blocked, holds)
        return legit_cache[key]

    base: list[Control] = []
    feedback: list[Refutation] = []
    tried: list[str] = []
    best_partial: _Evaluated | None = None
    for iteration in range(1, max_iterations + 1):
        gap = diagnosis["gap"]
        ctx = ProposalContext(
            iteration=iteration,
            gap=gap,
            diagnosis=diagnosis,
            base=base,
            feedback=feedback,
            tried=tried,
        )
        evaluated: list[_Evaluated] = []
        base_policy = Policy(
            version=f"{version}-base{iteration}",
            controls=parent.controls + base,
            parent=parent.version,
        )
        for proposal in proposer.propose(ctx):
            if len(evaluated) >= per_iteration:
                break
            tried.append(proposal.label)
            common = {
                "iteration": iteration,
                "gap": gap,
                "candidate": proposal.label,
                "base": [describe(c) for c in base],
                "source": proposal.source,
                "rationale": proposal.rationale,
            }
            findings = [
                f"{f.lint}: {f.message}"
                for c in proposal.controls
                for f in lint(c, profile.attacker_capabilities, [cx_result.exposure])
            ]
            if findings:
                record(LogEntry(**common, outcome="lint", detail=findings[0], lint=findings))
                feedback.append(
                    Refutation(candidate=proposal.label, outcome="lint", detail=findings[0])
                )
                continue

            controls = base + proposal.controls
            candidate = Policy(
                version=f"{version}-c{iteration}.{len(evaluated) + 1}",
                controls=parent.controls + controls,
                parent=parent.version,
            )
            factory = factory_for(candidate)

            # Cheapest decisive check first: does it break legitimate operations the base didn't?
            failed, blocked, holds = legit(candidate)
            new = sorted(set(failed) - set(legit(base_policy)[0]))
            if new:
                m = Measurement(
                    residual_exposure=0,
                    counterexamples=0,
                    legit_blocked=blocked,
                    legit_failed=len(failed),
                    holds=holds,
                    templates=len(controls),
                    params=_param_count(controls),
                )
                entry = record(
                    LogEntry(
                        **common,
                        outcome="false_positive",
                        detail=f"breaks {len(new)} legitimate operations: {', '.join(new[:4])}",
                        measurement=m,
                        score=score(m, risk),
                    )
                )
                feedback.append(
                    Refutation(
                        candidate=proposal.label, outcome="false_positive", detail=entry.detail
                    )
                )
                evaluated.append(_Evaluated(proposal=proposal, entry=entry))
                continue

            s = search(
                factory, scenario, seed=seed, depth=depth, workers=workers, labels=start_labels
            )
            beaten_by = s.best.moves if s.best else None
            residual, found_cx = sum(f.exposure for f in s.findings), len(s.findings)
            if beaten_by is None and injected is not None:
                # Search may not reach the injected threat (its moves can sit outside the
                # alphabet), so replay it directly.
                again = replay(seed, injected, sandbox=factory, days=days, labels=start_labels)
                if again.violations:
                    beaten_by, residual, found_cx = injected, again.exposure, 1
            m = Measurement(
                residual_exposure=residual,
                counterexamples=found_cx,
                legit_blocked=blocked,
                legit_failed=len(failed),
                holds=holds,
                templates=len(controls),
                params=_param_count(controls),
            )
            if beaten_by is None and failed:
                # Search can't beat it, but legitimate operations the base already broke are
                # still broken, and there's no counterexample to diagnose the next step from.
                entry = record(
                    LogEntry(
                        **common,
                        outcome="false_positive",
                        detail=f"no violation within depth {depth}, but {len(failed)} "
                        f"legitimate operations still fail: {', '.join(failed[:4])}",
                        measurement=m,
                        score=score(m, risk),
                    )
                )
                feedback.append(
                    Refutation(
                        candidate=proposal.label, outcome="false_positive", detail=entry.detail
                    )
                )
                evaluated.append(_Evaluated(proposal=proposal, entry=entry))
                continue
            if beaten_by is None:
                entry = record(
                    LogEntry(
                        **common,
                        outcome="survived",
                        detail=f"no violation within depth {depth} "
                        f"({s.explored:,} sequences); {holds} holds, "
                        f"{blocked} blocks on legitimate operations",
                        measurement=m,
                        score=score(m, risk),
                    )
                )
                evaluated.append(_Evaluated(proposal=proposal, entry=entry))
                continue
            moves, result, d = counterexample(factory, beaten_by)
            entry = record(
                LogEntry(
                    **common,
                    outcome="counterexample",
                    detail=(
                        f"search beats it in {len(moves)} move(s): "
                        + "; ".join(f"{mv.kind}@{mv.at}" for mv in moves)
                        + f" -> {', '.join(result.violated)}"
                        + (f" (gap: {d['gap']})" if d else "")
                    ),
                    counterexample=moves,
                    violated=result.violated,
                    measurement=m,
                    score=score(m, risk),
                )
            )
            feedback.append(
                Refutation(candidate=proposal.label, outcome="counterexample", detail=entry.detail)
            )
            evaluated.append(_Evaluated(proposal=proposal, entry=entry, diagnosis=d))

        survivors = [e for e in evaluated if e.entry.outcome == "survived"]
        if survivors:
            best = min(survivors, key=lambda e: rank(e.entry.measurement, risk))
            controls = base + best.proposal.controls
            policy = Policy(
                version=version,
                controls=parent.controls + controls,
                parent=parent.version,
                diff=[f"+ {describe(c)}" for c in controls],
            )
            return CEGISResult(
                status="repaired",
                iterations=iteration,
                log=log,
                policy=policy,
                chosen=[describe(c) for c in controls],
                score=best.entry.score,
                reason=f"{best.proposal.label} survived search and the regression suite",
                notes=getattr(proposer, "notes", []),
            )

        partial = [e for e in evaluated if e.entry.outcome == "counterexample" and e.diagnosis]
        if not partial:
            break
        best_partial = min(partial, key=lambda e: rank(e.entry.measurement, risk))
        base = base + best_partial.proposal.controls
        diagnosis = best_partial.diagnosis
        cx_result = replay(
            seed,
            best_partial.entry.counterexample or [],
            sandbox=factory_for(Policy(version="base", controls=parent.controls + base)),
            days=days,
            labels=start_labels,
        )

    kept = [describe(c) for c in base]
    return CEGISResult(
        status="cannot_auto_repair",
        iterations=min(len({e.iteration for e in log}), max_iterations),
        log=log,
        chosen=kept,
        reason=(
            "no candidate survived within templates after "
            f"{len({e.iteration for e in log})} iteration(s)"
            + (f"; the best partial fix was {' + '.join(kept)}" if kept else "")
        ),
        notes=getattr(proposer, "notes", []),
    )
