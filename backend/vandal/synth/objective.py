"""R8: the selection objective (DESIGN 9.4).

    min  ResidualExposure + lambda * LegitBlocked + mu * Holds

over candidates that survive the hard filter: no counterexample within depth k, and no
legitimate operation failed or broke an invariant. Every term is measured from real runs.
Ties go to fewer templates, then fewer parameters.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from vandal.contracts.entities import Cents
from vandal.twin.profile import RiskAppetite


class Measurement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    residual_exposure: Cents  # summed over every violating trace search still finds
    counterexamples: int
    legit_blocked: int  # legitimate operations blocked
    legit_failed: int  # legitimate operations not completed or completed wrongly
    holds: int  # friction on legitimate operations
    templates: int
    params: int

    @property
    def survives(self) -> bool:
        return self.counterexamples == 0 and self.legit_failed == 0


def score(m: Measurement, risk: RiskAppetite) -> Cents:
    return (
        m.residual_exposure + risk.lambda_per_blocked * m.legit_blocked + risk.mu_per_hold * m.holds
    )


def rank(m: Measurement, risk: RiskAppetite) -> tuple:
    """Sort key: survivors first, then the objective, then the simplest."""
    return (not m.survives, score(m, risk), m.templates, m.params)
