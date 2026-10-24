"""Composition root: wires the twin, Blue's gate, and an Operator into one runnable sandbox.

This is the one place that picks concrete implementations. twin/ search/ synth/ verify/ guard/
receive the Operator from here and never import it themselves.
"""

from __future__ import annotations

from dataclasses import dataclass

from vandal.contracts.interfaces import FinanceOperator
from vandal.guard.checks import v0_checks
from vandal.guard.gate import Gate
from vandal.operator.reference import ReferenceOperator, SimulatedApprover
from vandal.twin.flows import GatedTools
from vandal.twin.profile import Profile, load_profile
from vandal.twin.seed import DEFAULT_SEED, seed_state
from vandal.twin.world import Run, run_world


@dataclass
class Sandbox:
    profile: Profile
    run: Run
    gate: Gate
    tools: GatedTools
    operator: FinanceOperator
    approver: FinanceOperator

    def operate(self, days: int) -> Sandbox:
        run_world(self.run, self.tools, self.operator, self.approver, days)
        return self


def new_sandbox(profile: Profile | str = "bayline", seed: int = DEFAULT_SEED) -> Sandbox:
    profile = load_profile(profile) if isinstance(profile, str) else profile
    run = Run(seed_state(profile, seed=seed))
    gate = Gate(v0_checks(profile.approval_matrix))
    return Sandbox(
        profile=profile,
        run=run,
        gate=gate,
        tools=GatedTools(run, gate),
        operator=ReferenceOperator(profile),
        approver=SimulatedApprover(profile),
    )
