"""R2: the v0 controls (DESIGN 9.2), written as Checks.

v0 is a realistic mid-market setup: 3-way match within tolerance, approval above the threshold,
an exact-number duplicate check, and active vendors only. No T1, T2, or T3.
"""

from __future__ import annotations

from vandal.contracts.controls import Check, Condition, Predicate
from vandal.twin.profile import ApprovalMatrix


def _when(*conditions: tuple[str, str, object]) -> Predicate:
    return Predicate(all=[Condition(fact=f, op=op, value=v) for f, op, v in conditions])


def v0_checks(matrix: ApprovalMatrix) -> list[Check]:
    return [
        Check(
            id="v0.match.missing",
            stage="invoice.match",
            when=_when(("match.status", "in", ["no_po", "no_receipt"])),
            action="hold",
        ),
        Check(
            id="v0.match.tolerance",
            stage="invoice.match",
            when=_when(("match.variance_bps", "gt", matrix.match_tolerance_pct * 100)),
            action="hold",
        ),
        Check(
            id="v0.duplicate.exact_number",
            stage="invoice.match",
            when=_when(("invoice.duplicate_number", "eq", True)),
            action="block",
        ),
        Check(
            id="v0.vendor.active",
            stage="invoice.match",
            when=_when(("vendor.status", "ne", "active")),
            action="block",
        ),
        Check(
            id="v0.approval.threshold",
            stage="pre_approve",
            when=_when(
                ("tool", "eq", "approvals.request"), ("invoice.amount", "gt", matrix.threshold)
            ),
            action="escalate",
        ),
    ]
