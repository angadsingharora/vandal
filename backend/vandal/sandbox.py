"""Composition root: wires the twin, Blue's gate, and an Operator into one runnable sandbox.

This is the one place that picks concrete implementations. twin/ search/ synth/ verify/ guard/
receive the Operator from here and never import it themselves.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from vandal.contracts.events import Event
from vandal.contracts.interfaces import FinanceOperator
from vandal.guard.chain import RuntimeMonitor
from vandal.guard.gate import Gate
from vandal.operator.reference import ReferenceOperator, SimulatedApprover
from vandal.synth.templates import V0, Policy
from vandal.twin.flows import GatedTools
from vandal.twin.profile import Profile, load_profile
from vandal.twin.seed import DEFAULT_SEED, seed_state
from vandal.twin.world import Run, run_world
from vandal.verify.invariants import Limits, check
from vandal.verify.replay import RunResult, Trace, replay_trace


@dataclass
class Sandbox:
    profile: Profile
    policy: Policy
    run: Run
    gate: Gate
    tools: GatedTools
    operator: FinanceOperator
    approver: FinanceOperator

    def operate(self, days: int) -> Sandbox:
        run_world(self.run, self.tools, self.operator, self.approver, days)
        return self


def new_sandbox(
    profile: Profile | str = "bayline",
    seed: int = DEFAULT_SEED,
    *,
    policy: Policy | None = None,
    sink: Callable[[Event], None] | None = None,
    monitor: bool = False,
) -> Sandbox:
    """A fresh company under `policy` (v0 when omitted). `sink` sees every event. `monitor`
    turns on Blue's runtime invariant monitor (B2); search leaves it off for speed, since it
    checks the invariants at the end of every run anyway."""
    profile = load_profile(profile) if isinstance(profile, str) else profile
    watcher = None
    if monitor:
        limits = Limits.from_profile(profile)
        watcher = RuntimeMonitor(lambda state: check(state, None, limits))
    run = Run(seed_state(profile, seed=seed), sink=sink, monitor=watcher)
    policy = policy or V0
    gate = Gate(policy.checks(profile))
    return Sandbox(
        profile=profile,
        policy=policy,
        run=run,
        gate=gate,
        tools=GatedTools(run, gate),
        operator=ReferenceOperator(profile),
        approver=SimulatedApprover(profile),
    )


def replay_with_reference(trace: Trace, profile: Profile | str = "bayline") -> RunResult:
    """Replay a trace with the deterministic reference Operator (IMPLEMENTATION 0)."""
    loaded = load_profile(profile) if isinstance(profile, str) else profile
    return replay_trace(trace, sandbox=lambda seed: new_sandbox(loaded, seed=seed))
