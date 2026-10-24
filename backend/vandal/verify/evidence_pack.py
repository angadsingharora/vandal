"""R7: the evidence pack and the scorecard (DESIGN 10, 10.1).

The evidence pack is what a human approves: the counterexample, its diagnosis, every candidate
with its results, the chosen controls and their diff, the six verification checks, and the
scorecard before and after. It's plain JSON so the API and the UI can show it as is.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from vandal.contracts.entities import Cents
from vandal.contracts.moves import Move


class ClassResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempts: int
    succeeded: int
    exposure: Cents


class Scorecard(BaseModel):
    """One policy's numbers (DESIGN 10.1). Every number comes from a real run."""

    model_config = ConfigDict(extra="forbid")

    policy: str
    search_depth: int
    sequences_explored: int
    violations_found: int  # violating sequences from search
    attack_success: dict[str, ClassResult]  # by threat class, over the held-out variants
    attack_success_rate: float
    exposure: Cents  # in successful variants plus the worst search finding
    legit_operations: int  # regression cases run + seeded invoices replayed
    legit_failed: int  # not completed, or completed wrongly
    legit_blocked: int
    holds: int  # friction: holds on legitimate operations (some clear the same step)
    false_positive_rate: float  # legit_failed / legit_operations
    broken_invariants: list[str]  # in any legitimate run
    extraction_accuracy: float | None = None
    gl_coding_accuracy: float | None = None
    planted_discrepancies_caught: float | None = None
    notes: list[str] = []


class CheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int
    name: str
    passed: bool
    detail: str
    data: dict[str, Any] = {}


class Counterexample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    moves: list[Move]
    violated: list[str]
    exposure: Cents
    found_under: str


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str  # "manual", or the CEGIS iteration that proposed it (R8)
    controls: list[str]
    lint: list[str]
    result: str


class EvidencePack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    parent: str | None
    profile: str
    seed: int
    counterexample: Counterexample | None
    diagnosis: dict[str, Any] | None
    candidates: list[Candidate]
    chosen: list[str]
    diff: list[str]
    checks: list[CheckResult]
    metrics: dict[str, Scorecard]  # "before" (the parent) and "after" (this policy)
    approvable: bool  # every check passed and no lint rejected a control

    def write(self, out_dir: str | Path) -> Path:
        path = Path(out_dir) / f"{self.version}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.model_dump(mode="json"), indent=2) + "\n")
        return path
